// The contact form. A message goes by email to the maintainer and is never stored; the
// only thing kept is a keyed hash of the sender's IP address with the time, for a day,
// so one sender can't flood the inbox. The maintainer's address is a deployment secret
// (CONTACT_TO), never part of the code or the page.

export const KINDS = {
  problem: "Bug report",
  idea: "Idea",
  question: "Question",
  partnership: "Partnership or press",
  other: "Other",
} as const;
export type Kind = keyof typeof KINDS;

export const MAX_MESSAGE = 4000;
export const PER_SENDER_PER_HOUR = 5;
export const ALL_PER_DAY = 100;

export interface ContactInput {
  kind?: unknown;
  message?: unknown;
  email?: unknown;
  page?: unknown;
  /** Honeypot: a field people never see. Anything in it means a bot filled the form. */
  website?: unknown;
  turnstile_token?: unknown;
}

export interface ContactFields {
  kind: Kind;
  message: string;
  email: string | null;
  page: string | null;
}

/** Rate-limit memory: keyed IP hashes and times only. */
export interface ContactWindow {
  hourSince: string;
  perSender: number;
  daySince: string;
  perDay: number;
}

export interface ContactLog {
  countSince(ipHash: string | null, since: string): Promise<number>;
  record(ipHash: string, at: string): Promise<void>;
  /** Record a message only if the sender and the day both have room, checked and recorded in
   *  one step so a burst of parallel posts can't all pass. */
  reserve(ipHash: string, at: string, limits: ContactWindow): Promise<"ok" | "sender" | "global">;
  /** Give back a reservation whose message couldn't be sent. */
  release(ipHash: string, at: string): Promise<void>;
  prune(before: string): Promise<void>;
}

/** Sends one raw RFC 5322 message (in production, Cloudflare Email Routing). */
export type SendMail = (raw: string, from: string, to: string) => Promise<void>;

export class ContactError extends Error {
  status: number;

  constructor(message: string, status = 400) {
    super(message);
    this.status = status;
  }
}

const EMAIL = /^[^\s@<>()",;:\\[\]]{1,64}@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}$/;
const PAGE = /^\/[A-Za-z0-9/_\-.]{0,199}$/;

/** Validate the form. Returns null for a honeypot hit, which is accepted silently. */
export function validateContact(input: ContactInput): ContactFields | null {
  if (typeof input.website === "string" && input.website.trim()) return null;
  const kind = String(input.kind ?? "");
  if (!(kind in KINDS)) throw new ContactError("Choose what your message is about.");
  const message = typeof input.message === "string" ? input.message.replace(/\r\n?/g, "\n").trim() : "";
  if (message.length < 10) throw new ContactError("Please write a little more, so we can help.");
  if (message.length > MAX_MESSAGE) throw new ContactError(`Messages are limited to ${MAX_MESSAGE} characters.`);
  const rawEmail = typeof input.email === "string" ? input.email.trim() : "";
  if (rawEmail && (rawEmail.length > 254 || !EMAIL.test(rawEmail))) {
    throw new ContactError("That email address doesn't look right. Leave it empty if you don't need a reply.");
  }
  const rawPage = typeof input.page === "string" ? input.page.trim() : "";
  return {
    kind: kind as Kind,
    message,
    email: rawEmail || null,
    page: PAGE.test(rawPage) ? rawPage : null,
  };
}

/** Base64 of UTF-8 text in 76-character lines, so any message is safe in an email body. */
export function base64Lines(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return (btoa(binary).match(/.{1,76}/g) ?? []).join("\r\n");
}

/** The email the maintainer receives. Only validated values reach a header. */
export function buildMessage(
  fields: ContactFields,
  options: { from: string; to: string; id: string; now: Date; host: string },
): string {
  const body = [
    fields.message,
    "",
    "--",
    `Kind: ${KINDS[fields.kind]}`,
    `Reply to: ${fields.email ?? "(no address given; no reply expected)"}`,
    `Page: ${fields.page ?? "(not given)"}`,
    "Sent from the CompactBench contact form. The site does not keep a copy.",
  ].join("\n");
  const headers = [
    `From: CompactBench contact form <${options.from}>`,
    `To: <${options.to}>`,
    ...(fields.email ? [`Reply-To: <${fields.email}>`] : []),
    `Subject: [CompactBench] ${KINDS[fields.kind]}`,
    `Date: ${options.now.toUTCString()}`,
    `Message-ID: <${options.id}@${options.host}>`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
  ];
  return `${headers.join("\r\n")}\r\n\r\n${base64Lines(body)}\r\n`;
}

/** Who counts as one sender: an IPv4 address, or an IPv6 /64 (one host can use its whole /64,
 *  so per-address counting would let it rotate past the limit). */
export function senderNetwork(ip: string): string {
  if (ip.includes(".")) return ip.slice(ip.lastIndexOf(":") + 1);
  if (!ip.includes(":")) return ip;
  const [head = "", tail = ""] = ip.split("::");
  const h = head ? head.split(":") : [];
  const t = ip.includes("::") && tail ? tail.split(":") : [];
  const groups = ip.includes("::") ? [...h, ...Array(Math.max(0, 8 - h.length - t.length)).fill("0"), ...t] : h;
  return `${groups.slice(0, 4).map((g) => (Number.parseInt(g, 16) || 0).toString(16)).join(":")}::/64`;
}

/** Keyed hash of the sender's network: enough to count, useless for finding anyone. */
export async function hashIp(secret: string, ip: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(`contact:${secret}`), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(senderNetwork(ip)));
  return Array.from(new Uint8Array(mac).slice(0, 16), (b) => b.toString(16).padStart(2, "0")).join("");
}

export interface ContactContext {
  log: ContactLog;
  send: SendMail;
  from: string;
  to: string;
  secret: string;
  ip: string;
  host: string;
  now?: Date;
}

/** Check, rate-limit and send one message. Throws ContactError. */
export async function contact(input: ContactInput, ctx: ContactContext): Promise<"sent" | "ignored"> {
  const fields = validateContact(input);
  if (!fields) return "ignored";
  const now = ctx.now ?? new Date();
  const ipHash = await hashIp(ctx.secret, ctx.ip);
  const hourAgo = new Date(now.getTime() - 3_600_000).toISOString();
  const dayAgo = new Date(now.getTime() - 86_400_000).toISOString();
  const busySender = () => new ContactError("You've sent several messages in the last hour. Please try again later.", 429);
  const busyDay = () =>
    new ContactError("The contact form is busy today. Please try again tomorrow, or open an issue on GitHub.", 429);
  if ((await ctx.log.countSince(ipHash, hourAgo)) >= PER_SENDER_PER_HOUR) throw busySender();
  if ((await ctx.log.countSince(null, dayAgo)) >= ALL_PER_DAY) throw busyDay();
  // Take this message's place in the limits before sending, so parallel posts can't all send.
  const at = now.toISOString();
  const slot = await ctx.log.reserve(ipHash, at, {
    hourSince: hourAgo,
    perSender: PER_SENDER_PER_HOUR,
    daySince: dayAgo,
    perDay: ALL_PER_DAY,
  });
  if (slot === "sender") throw busySender();
  if (slot === "global") throw busyDay();
  const id = crypto.randomUUID();
  try {
    await ctx.send(buildMessage(fields, { from: ctx.from, to: ctx.to, id, now, host: ctx.host }), ctx.from, ctx.to);
  } catch (error) {
    await ctx.log.release(ipHash, at);
    throw error;
  }
  await ctx.log.prune(dayAgo);
  return "sent";
}

/** In-memory log for tests and local development. */
export class MemoryContactLog implements ContactLog {
  rows: { ipHash: string; at: string }[] = [];

  async countSince(ipHash: string | null, since: string): Promise<number> {
    return this.rows.filter((r) => (ipHash === null || r.ipHash === ipHash) && r.at >= since).length;
  }
  async record(ipHash: string, at: string): Promise<void> {
    this.rows.push({ ipHash, at });
  }
  async reserve(ipHash: string, at: string, l: ContactWindow): Promise<"ok" | "sender" | "global"> {
    // No await between the checks and the push, so parallel calls can't interleave.
    if (this.rows.filter((r) => r.ipHash === ipHash && r.at >= l.hourSince).length >= l.perSender) return "sender";
    if (this.rows.filter((r) => r.at >= l.daySince).length >= l.perDay) return "global";
    this.rows.push({ ipHash, at });
    return "ok";
  }
  async release(ipHash: string, at: string): Promise<void> {
    const i = this.rows.findIndex((r) => r.ipHash === ipHash && r.at === at);
    if (i >= 0) this.rows.splice(i, 1);
  }
  async prune(before: string): Promise<void> {
    this.rows = this.rows.filter((r) => r.at >= before);
  }
}
