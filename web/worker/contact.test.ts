// node --test worker/contact.test.ts  (Node 24 strips the types)
import assert from "node:assert/strict";
import { test } from "node:test";
import { handleApi, type ApiEnv } from "./api.ts";
import { buildMessage, contact, ContactError, MemoryContactLog, PER_SENDER_PER_HOUR, validateContact } from "./contact.ts";
import { MemoryStore } from "./store.ts";

const ORIGIN = "https://compactbench.test";
const env = {
  SESSION_SECRET: "s".repeat(32),
  CONTACT_TO: "owner@example.org",
  CONTACT_FROM: "contact@compactbench.test",
} as unknown as ApiEnv;

function setup(withMail = true) {
  const sent: { raw: string; from: string; to: string }[] = [];
  const log = new MemoryContactLog();
  const deps = {
    store: new MemoryStore(),
    contactLog: log,
    sendMail: withMail ? async (raw: string, from: string, to: string) => void sent.push({ raw, from, to }) : undefined,
  };
  const post = (body: unknown, ip = "203.0.113.7", origin = ORIGIN) =>
    handleApi(
      new Request(`${ORIGIN}/api/contact`, {
        method: "POST",
        headers: { Origin: origin, "Content-Type": "application/json", "CF-Connecting-IP": ip },
        body: JSON.stringify(body),
      }),
      env,
      deps,
    ) as Promise<Response>;
  return { sent, log, post };
}

const message = { kind: "problem", message: "The leaderboard CSV has an empty column.", email: "dev@example.com", page: "/data" };

test("a message is emailed to the maintainer and only a hashed sender is kept", async () => {
  const { sent, log, post } = setup();
  const response = await post(message);
  assert.equal(response.status, 200);
  assert.equal(sent.length, 1);
  assert.equal(sent[0]!.to, "owner@example.org");
  const raw = sent[0]!.raw;
  assert.match(raw, /^From: CompactBench contact form <contact@compactbench\.test>\r\n/);
  assert.match(raw, /\r\nReply-To: <dev@example\.com>\r\n/);
  assert.match(raw, /\r\nSubject: \[CompactBench\] Bug report\r\n/);
  const body = Buffer.from(raw.split("\r\n\r\n")[1]!.replace(/\r\n/g, ""), "base64").toString("utf8");
  assert.match(body, /empty column/);
  assert.match(body, /Page: \/data/);
  assert.equal(log.rows.length, 1);
  assert.doesNotMatch(log.rows[0]!.ipHash, /203\.0\.113\.7/);
  assert.doesNotMatch(JSON.stringify(log.rows), /empty column|dev@example/);
});

test("the maintainer's address never reaches the visitor", async () => {
  const { post } = setup();
  const text = await (await post(message)).text();
  assert.doesNotMatch(text, /owner@example\.org/);
});

test("not set up yet, cross-site, honeypot and bad input", async () => {
  assert.equal((await setup(false).post(message)).status, 503);
  const { sent, post } = setup();
  assert.equal((await post(message, "1.1.1.1", "https://evil.test")).status, 403);
  assert.equal((await post({ ...message, website: "http://spam" })).status, 200, "bots get no hint");
  assert.equal(sent.length, 0, "and nothing is sent");
  assert.equal((await post({ ...message, kind: "sales" })).status, 400);
  assert.equal((await post({ ...message, message: "hi" })).status, 400);
  assert.equal((await post({ ...message, email: "not an email" })).status, 400);
});

test("one sender is limited per hour", async () => {
  const { post } = setup();
  for (let i = 0; i < PER_SENDER_PER_HOUR; i++) assert.equal((await post(message)).status, 200);
  assert.equal((await post(message)).status, 429);
  assert.equal((await post(message, "198.51.100.9")).status, 200, "someone else can still write");
});

test("headers can't be injected through the email or page", () => {
  assert.throws(() => validateContact({ ...message, email: "a@b.co\r\nBcc: x@y.z" }), ContactError);
  const fields = validateContact({ ...message, page: "/data\r\nX-Evil: 1" })!;
  assert.equal(fields.page, null);
  const raw = buildMessage(fields, { from: "f@x.test", to: "t@x.test", id: "1", now: new Date(0), host: "x.test" });
  assert.equal(raw.split("\r\n\r\n")[0]!.split("\r\n").length, 9, "exactly the expected headers");
});

test("old rate-limit rows are pruned after a day", async () => {
  const log = new MemoryContactLog();
  await log.record("old", "2026-01-01T00:00:00.000Z");
  await contact(message, {
    log, send: async () => {}, from: "f@x.test", to: "t@x.test", secret: "k", ip: "1.2.3.4", host: "x.test",
    now: new Date("2026-01-03T00:00:00Z"),
  });
  assert.deepEqual(log.rows.map((r) => r.at), ["2026-01-03T00:00:00.000Z"]);
});
