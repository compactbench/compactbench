// node --test admin/test/*.test.ts  (Node 24 strips the types)
import assert from "node:assert/strict";
import { test } from "node:test";
import { verifyAccess } from "../src/access.ts";
import { csvCell, type Env, exportSubmissions, familyDifficulty, flagRows, render, type Row, summarize } from "../src/worker.ts";

const TEAM = "team.cloudflareaccess.com";
const AUD = "aud-123";
const OWNER = "owner@example.com";
const config = { teamDomain: TEAM, audience: AUD, ownerEmail: OWNER };

const enc = (data: Uint8Array | string) =>
  Buffer.from(typeof data === "string" ? new TextEncoder().encode(data) : data)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

async function setup() {
  const pair = (await crypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true,
    ["sign", "verify"],
  )) as CryptoKeyPair;
  const jwk = { ...(await crypto.subtle.exportKey("jwk", pair.publicKey)), kid: "k1" };
  const fetcher = (async () => Response.json({ keys: [jwk] })) as unknown as typeof fetch;
  const sign = async (claims: Record<string, unknown>, kid = "k1") => {
    const head = enc(JSON.stringify({ alg: "RS256", kid }));
    const body = enc(JSON.stringify(claims));
    const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", pair.privateKey, new TextEncoder().encode(`${head}.${body}`));
    return `${head}.${body}.${enc(new Uint8Array(sig))}`;
  };
  return { fetcher, sign };
}

const good = { aud: [AUD], iss: `https://${TEAM}`, email: OWNER, exp: 2_000_000_000 };

test("accepts the owner's valid token", async () => {
  const { fetcher, sign } = await setup();
  assert.equal(await verifyAccess(await sign(good), config, fetcher, 1_900_000_000), OWNER);
});

test("rejects anyone else, expired, wrong audience or issuer, and tampering", async () => {
  const { fetcher, sign } = await setup();
  const now = 1_900_000_000;
  assert.equal(await verifyAccess(await sign({ ...good, email: "x@example.com" }), config, fetcher, now), null);
  assert.equal(await verifyAccess(await sign({ ...good, exp: now - 1 }), config, fetcher, now), null);
  assert.equal(await verifyAccess(await sign({ ...good, aud: ["other"] }), config, fetcher, now), null);
  assert.equal(await verifyAccess(await sign({ ...good, iss: "https://evil.example" }), config, fetcher, now), null);
  assert.equal(await verifyAccess(await sign(good, "unknown-kid"), config, fetcher, now), null);
  const token = await sign(good);
  const [h, , s] = token.split(".");
  const forged = `${h}.${enc(JSON.stringify({ ...good, email: OWNER, exp: 2_100_000_000 }))}.${s}`;
  assert.equal(await verifyAccess(forged, config, fetcher, now), null);
  assert.equal(await verifyAccess(null, config, fetcher, now), null);
  assert.equal(await verifyAccess("not.a.jwt.token", config, fetcher, now), null);
});

test("summary reads submissions, flags stuck runs and survives GitHub errors", async () => {
  const now = Date.parse("2026-11-01T12:00:00Z");
  const sub = (id: string, status: string, created: string, updated = created) => ({
    id, handle: "a", method_name: "m", method_version: "1", provider: "openai", model: "gpt", model_label: null,
    status, message: null, score: null, created_at: created, updated_at: updated,
  });
  const rows = [
    sub("fresh", "running", "2026-11-01T11:00:00Z"),
    sub("stale", "building", "2026-11-01T02:00:00Z"),
    sub("done", "failed", "2026-10-29T00:00:00Z"),
  ];
  let bound: unknown[] = [];
  const DB = {
    prepare: () => ({
      bind: (...values: unknown[]) => {
        bound = values;
        return { all: async <T>() => ({ results: rows as T[] }) };
      },
    }),
  };
  const env: Env = {
    ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: AUD, OWNER_EMAIL: OWNER,
    GITHUB_REPO: "o/r", SITE_URL: "https://site.example", DB,
  };
  const fetcher = (async (input: string | URL) => {
    const url = String(input);
    if (url.includes("/actions/")) return new Response("nope", { status: 500 });
    return Response.json({ entries: [] });
  }) as unknown as typeof fetch;
  const summary = await summarize(env, fetcher, now);
  assert.equal(bound[0], "2026-10-25T12:00:00.000Z");
  assert.deepEqual(summary.submissions.map((s) => [s.id, s.stuck]), [["fresh", false], ["stale", true], ["done", false]]);
  assert.deepEqual(summary.counts, { day: 2, week: 3, active: 2, failed_week: 1 });
  assert.equal(summary.runs.length, 0);
  assert.equal(summary.errors.length, 1);
  const html = render(summary, OWNER, env.SITE_URL);
  assert.match(html, /building — stuck\?/);
  assert.match(html, /https:\/\/site\.example\/status\?id=stale/);
});

test("render escapes everything that comes from submitters and GitHub", () => {
  const html = render(
    {
      submissions: [{
        id: "abc\"><x", handle: "<b>", method_name: "<script>alert(1)</script>", method_version: "1", provider: "custom",
        model: "m", model_label: "<i>label", status: "failed", message: "\"><img src=x onerror=alert(1)>", score: null,
        created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z", stuck: false,
      }],
      counts: { day: 1, week: 1, active: 0, failed_week: 1 },
      runs: [{ id: 1, url: "javascript:x\"", title: "<u>", status: "completed", conclusion: "failure", started: "2026-11-01T00:00:00Z", minutes: 3 }],
      leaderboard: [],
      families: [{ family: "<f>", best: 0.5, best_method: "<m>", median: 0.4, rows: 2 }],
      flags: [{ method: "<script>x</script>", reason: "<b>" }],
      errors: [],
    },
    OWNER,
  );
  assert.doesNotMatch(html, /<script>alert/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<img|<i>|<b>|<u>/);
  assert.doesNotMatch(html, /href="javascript:/);
  assert.match(html, /status\?id=abc%22%3E%3Cx/);
});

const row = (kind: string, name: string, score: number, by_family: Record<string, number>, handle: string | null = null): Row => ({
  method_name: name, method_version: "1.0.0", row_kind: kind, handle, compactor_model: "m", score,
  score_ci_low: score - 0.02, score_ci_high: score + 0.02, by_family, season: "s1", published_at: "2026-11-01T00:00:00Z",
});

test("family difficulty and review flags", () => {
  const rows = [
    row("baseline", "a", 0.5, { x: 0.6, y: 0.2 }),
    row("baseline", "b", 0.4, { x: 0.4, y: 0.3 }),
    row("control", "oracle", 0.99, { x: 1, y: 1 }),
    row("submission", "spiky", 0.45, { x: 0.95, y: 0.1 }, "eve"),
    row("submission", "great", 0.75, { x: 0.8, y: 0.7 }, "ann"),
  ];
  const stats = familyDifficulty(rows);
  assert.deepEqual(stats.map((f) => [f.family, f.best, f.best_method, f.rows]), [["y", 0.7, "@ann/great", 4], ["x", 0.95, "@eve/spiky", 4]]);
  assert.equal(stats[0]!.median, 0.25);
  const flags = flagRows(rows);
  assert.deepEqual(flags.map((f) => f.method), ["@eve/spiky 1.0.0", "@ann/great 1.0.0"]);
  assert.match(flags[0]!.reason, /x at 95 vs 45 overall/);
  assert.match(flags[1]!.reason, /leads the best baseline by 25 points/);
});

test("the submissions export guards spreadsheet formulas", async () => {
  assert.equal(csvCell("=HYPERLINK(1)"), "'=HYPERLINK(1)");
  assert.equal(csvCell(-0.5), "-0.5");
  assert.equal(csvCell('a,"b"'), '"a,""b"""');
  const DB = {
    prepare: () => ({
      bind: () => ({
        all: async <T>() => ({
          results: [{ id: "x1", handle: "eve", method_name: "m", method_version: "1", provider: "custom", model: "m", model_label: "+cmd", status: "failed", message: "a,b", score: null, created_at: "c", updated_at: "u" }] as T[],
        }),
      }),
    }),
  };
  const csv = await exportSubmissions(DB);
  assert.match(csv.split("\r\n")[0]!, /^id,handle,method_name/);
  assert.match(csv, /'\+cmd/);
  assert.match(csv, /"a,b"/);
});
