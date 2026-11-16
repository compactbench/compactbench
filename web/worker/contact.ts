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
export interface ContactLog {
  countSince(ipHash: string | null, since: string): Promise<number>;
  record(ipHash: string, at: string): Promise<void>;
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

/** Keyed hash of the sender's IP: enough to count, useless for finding anyone. */
export async function hashIp(secret: string, ip: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(`contact:${secret}`), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(ip));
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
  if ((await ctx.log.countSince(ipHash, hourAgo)) >= PER_SENDER_PER_HOUR) {
    throw new ContactError("You've sent several messages in the last hour. Please try again later.", 429);
  }
  if ((await ctx.log.countSince(null, dayAgo)) >= ALL_PER_DAY) {
    throw new ContactError("The contact form is busy today. Please try again tomorrow, or open an issue on GitHub.", 429);
  }
  const id = crypto.randomUUID();
  await ctx.send(buildMessage(fields, { from: ctx.from, to: ctx.to, id, now, host: ctx.host }), ctx.from, ctx.to);
  await ctx.log.record(ipHash, now.toISOString());
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
  async prune(before: string): Promise<void> {
    this.rows = this.rows.filter((r) => r.at >= before);
  }
}
