// node --test web/worker/*.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { type ApiEnv, handleApi } from "./api.ts";
import { MemoryStore, STALE_AFTER_MS, STALE_MESSAGE, type SubmissionRecord } from "./store.ts";

const ORIGIN = "https://compactbench.test";

const b64url = (bytes: Uint8Array) =>
  Buffer.from(bytes).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function seasonKey(): Promise<string> {
  const pair = (await crypto.subtle.generateKey({ name: "X25519" }, true, ["deriveBits"])) as CryptoKeyPair;
  return b64url(new Uint8Array(await crypto.subtle.exportKey("raw", pair.publicKey)));
}

async function oidc() {
  const pair = (await crypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true,
    ["sign", "verify"],
  )) as CryptoKeyPair;
  const jwk = { ...(await crypto.subtle.exportKey("jwk", pair.publicKey)), kid: "gh" };
  const sign = async (claims: Record<string, unknown>) => {
    const head = b64url(new TextEncoder().encode(JSON.stringify({ alg: "RS256", kid: "gh" })));
    const body = b64url(new TextEncoder().encode(JSON.stringify(claims)));
    const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", pair.privateKey, new TextEncoder().encode(`${head}.${body}`));
    return `${head}.${body}.${b64url(new Uint8Array(sig))}`;
  };
  return { jwk, sign };
}

async function setup(overrides: Partial<ApiEnv> = {}) {
  const store = new MemoryStore();
  const { jwk, sign } = await oidc();
  const dispatched: string[] = [];
  const github = { dispatchStatus: 204 };
  const fetcher = (async (input: string | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("login/oauth/access_token")) return Response.json({ access_token: "gho_x" });
    if (url === "https://api.github.com/user") return Response.json({ login: "alice", id: 42 });
    if (url.endsWith("/dispatches")) {
      if (github.dispatchStatus !== 204) return new Response(null, { status: github.dispatchStatus });
      dispatched.push(JSON.parse(String(init?.body)).inputs.submission_id);
      return new Response(null, { status: 204 });
    }
    if (url.endsWith("/.well-known/jwks")) return Response.json({ keys: [jwk] });
    if (url.endsWith("/turnstile/v0/siteverify")) {
      const body = init?.body as FormData;
      return Response.json({ success: body.get("secret") === "ts-secret" && body.get("response") === "good" });
    }
    throw new Error(`unexpected fetch ${url}`);
  }) as unknown as typeof fetch;
  const env: ApiEnv = {
    GITHUB_CLIENT_ID: "cid",
    GITHUB_CLIENT_SECRET: "csecret",
    SESSION_SECRET: "session-secret-for-tests",
    SEASON_KEY: "s1",
    SEASON_PUBLIC_KEY: await seasonKey(),
    GITHUB_REPO: "compactbench/compactbench",
    GITHUB_DISPATCH_TOKEN: "dispatch",
    OIDC_AUDIENCE: ORIGIN,
    ...overrides,
  };
  const call = async (path: string, init: RequestInit = {}) =>
    (await handleApi(new Request(ORIGIN + path, init), env, { store, fetcher })) as Response;
  const signIn = async () => {
    const start = await call("/auth/github");
    const stateCookie = start.headers.get("Set-Cookie")!.split(";")[0]!;
    const state = new URL(start.headers.get("Location")!).searchParams.get("state");
    const back = await call(`/auth/callback?code=abc&state=${state}`, { headers: { Cookie: stateCookie } });
    const session = back.headers.getSetCookie().find((c) => c.startsWith("cb_session="))!;
    return session.split(";")[0]!;
  };
  const workflowToken = (extra: Record<string, unknown> = {}) =>
    sign({
      iss: "https://token.actions.githubusercontent.com",
      aud: ORIGIN,
      repository: "compactbench/compactbench",
      ref: "refs/heads/main",
      workflow_ref: "compactbench/compactbench/.github/workflows/evaluate-submission.yml@refs/heads/main",
      exp: Math.floor(Date.now() / 1000) + 300,
      ...extra,
    });
  return { store, env, call, signIn, dispatched, workflowToken, github };
}

const form = {
  method_name: "ledger",
  method_version: "1.0.0",
  class_name: "Ledger",
  provider: "openrouter",
  model: "qwen/qwen3-235b",
  method_py: "class Ledger: ...\n",
  requirements: "tiktoken==0.12.0\n",
  method_key: "sk-or-v1-abcdef123456",
  reader_key: "sk-ant-api03-abcdef123456",
};

const post = (cookie: string, body: unknown, origin = ORIGIN): RequestInit => ({
  method: "POST",
  headers: { Cookie: cookie, Origin: origin, "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

test("GitHub sign-in sets a session that /api/me reads", async () => {
  const { call, signIn } = await setup();
  const session = await signIn();
  const me = await call("/api/me", { headers: { Cookie: session } });
  assert.deepEqual(await me.json(), { login: "alice" });
  assert.equal((await call("/api/me")).status, 401);
});

test("a callback with the wrong state is refused", async () => {
  const { call } = await setup();
  assert.equal((await call("/auth/callback?code=abc&state=forged")).status, 400);
});

test("a submission is sealed, stored, rate-limited and dispatched", async () => {
  const { call, signIn, store, dispatched } = await setup();
  const session = await signIn();
  assert.equal((await call("/api/submissions", post("", form))).status, 401);
  assert.equal((await call("/api/submissions", post(session, form, "https://evil.test"))).status, 403);

  const created = await call("/api/submissions", post(session, form));
  assert.equal(created.status, 201);
  const { id } = (await created.json()) as { id: string };
  assert.deepEqual(dispatched, [id]);
  const bundle = await store.getBundle(id);
  assert.ok(bundle);
  assert.doesNotMatch(bundle, /sk-or-v1|sk-ant-api03/, "plain keys never stored");
  const parsed = JSON.parse(bundle);
  assert.match(parsed.sealed_method_key, /^cbseal1:/);
  assert.match(parsed.sealed_reader_key, /^cbseal1:/);
  assert.equal(parsed.handle, "alice");

  const again = await call("/api/submissions", post(session, form));
  assert.equal(again.status, 429, "one run at a time");

  const status = await call(`/api/submissions/${id}`);
  const view = (await status.json()) as Record<string, unknown>;
  assert.equal(view.status, "queued");
  assert.equal(view.github_id, undefined);
});

test("a submission that can't be started is forgotten and doesn't count", async () => {
  const { call, signIn, store, dispatched, github } = await setup({ LIMIT_PER_WEEK: "1" });
  const session = await signIn();
  github.dispatchStatus = 401;
  const failed = await call("/api/submissions", post(session, form));
  assert.equal(failed.status, 503);
  assert.match(((await failed.json()) as { error: string }).error, /doesn't count/);
  assert.equal(store.records.size, 0, "no record");
  assert.equal(store.bundles.size, 0, "no sealed keys left behind");

  github.dispatchStatus = 204;
  const retried = await call("/api/submissions", post(session, form));
  assert.equal(retried.status, 201, "neither in progress nor counted toward the week");
  assert.equal(dispatched.length, 1);
});

test("validation and the kill switch", async () => {
  const { call, signIn } = await setup();
  const session = await signIn();
  const bad = async (body: Record<string, unknown>) => (await call("/api/submissions", post(session, { ...form, ...body }))).status;
  assert.equal(await bad({ requirements: "torch>=2\n" }), 400);
  assert.equal(await bad({ reader_key: "" }), 400);
  assert.equal(await bad({ model_label: "GPT-9" }), 400);
  assert.equal(await bad({ provider: "ollama" }), 400);
  assert.equal(await bad({ provider: "custom", base_url: "http://x.test/v1", method_key: "" }), 400);
  const custom = await call(
    "/api/submissions",
    post(session, { ...form, provider: "custom", base_url: "https://models.example.com/v1", model_label: "Acme v2", method_key: "" }),
  );
  assert.equal(custom.status, 201);

  const closed = await setup({ SUBMISSIONS_OPEN: "false" });
  const s2 = await closed.signIn();
  assert.equal((await closed.call("/api/submissions", post(s2, form))).status, 503);

  // While closed, only logins on the early-access list may submit (the launch smoke test).
  const others = await setup({ SUBMISSIONS_OPEN: "false", SUBMISSIONS_EARLY_ACCESS: "bob, carol" });
  assert.equal((await others.call("/api/submissions", post(await others.signIn(), form))).status, 503);
  const early = await setup({ SUBMISSIONS_OPEN: "false", SUBMISSIONS_EARLY_ACCESS: "bob, Alice" });
  assert.equal((await early.call("/api/submissions", post(await early.signIn(), form))).status, 201);
});

test("with Turnstile on, a submission needs a valid token", async () => {
  const { call, signIn } = await setup({ TURNSTILE_SECRET: "ts-secret" });
  const session = await signIn();
  assert.equal((await call("/api/submissions", post(session, form))).status, 403);
  assert.equal((await call("/api/submissions", post(session, { ...form, turnstile_token: "bad" }))).status, 403);
  assert.equal((await call("/api/submissions", post(session, { ...form, turnstile_token: "good" }))).status, 201);
});

test("internal endpoints accept only the evaluate workflow on main", async () => {
  const { call, signIn, workflowToken } = await setup();
  const session = await signIn();
  const { id } = (await (await call("/api/submissions", post(session, form))).json()) as { id: string };
  const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

  assert.equal((await call(`/api/internal/bundles/${id}`)).status, 403);
  assert.equal((await call(`/api/internal/bundles/${id}`, auth(await workflowToken({ ref: "refs/heads/feature" })))).status, 403);
  assert.equal(
    (await call(`/api/internal/bundles/${id}`, auth(await workflowToken({ repository: "mallory/fork" })))).status,
    403,
  );
  const ok = await call(`/api/internal/bundles/${id}`, auth(await workflowToken()));
  assert.equal(ok.status, 200);
  assert.equal(((await ok.json()) as { id: string }).id, id);

  const update = await call(`/api/internal/submissions/${id}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${await workflowToken()}`, "Content-Type": "application/json" },
    body: JSON.stringify({ status: "published", score: 0.42 }),
  });
  assert.equal(update.status, 200);
  const view = (await (await call(`/api/submissions/${id}`)).json()) as { status: string; score: number };
  assert.equal(view.status, "published");
  assert.equal(view.score, 0.42);
});

test("a finished run's sealed files go to the private archive, only from the evaluate workflow", async () => {
  const { call, signIn, workflowToken, store } = await setup();
  const session = await signIn();
  const { id } = (await (await call("/api/submissions", post(session, form))).json()) as { id: string };
  const put = async (name: string, body: BodyInit, token: string | null, target = id) =>
    call(`/api/internal/archive/${target}/${name}`, {
      method: "PUT",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body,
    });
  const sealed = new Uint8Array([1, 2, 3, 4]);

  assert.equal((await put("traces.sealed", sealed, null)).status, 403);
  assert.equal((await put("traces.sealed", sealed, await workflowToken({ ref: "refs/heads/feature" }))).status, 403);
  assert.equal((await put("traces.sealed", sealed, await workflowToken(), "aaaaaaaaaaaaaaaa")).status, 404);
  assert.equal((await put("bundle.json", sealed, await workflowToken())).status, 400);
  assert.equal((await put("traces.sealed", new Uint8Array(), await workflowToken())).status, 400);
  assert.equal(store.archived.size, 0);

  const ok = await put("traces.sealed", sealed, await workflowToken());
  assert.equal(ok.status, 200);
  assert.deepEqual(new Uint8Array(store.archived.get(`runs/s1/${id}/traces.sealed`)!), sealed);
});

test("a reference-method submission runs a built-in on the submitter's model, with no code", async () => {
  const { call, signIn, store } = await setup();
  const session = await signIn();
  const reference = {
    reference_method: "sectioned-summary",
    provider: "openrouter",
    model: "qwen/qwen3-235b",
    // Anything sent for an uploaded method is ignored.
    method_name: "ignored",
    method_py: "import os\n",
    requirements: "torch==2.0.0\n",
    method_config: { reasoning_effort: "high" },
    method_key: form.method_key,
    reader_key: form.reader_key,
  };
  const created = await call("/api/submissions", post(session, reference));
  assert.equal(created.status, 201);
  const { id } = (await created.json()) as { id: string };
  const parsed = JSON.parse((await store.getBundle(id)) ?? "{}");
  assert.equal(parsed.reference_method, "sectioned-summary");
  assert.equal(parsed.method_name, "sectioned-summary");
  assert.equal(parsed.method_version, "1.0.0");
  assert.equal(parsed.class_name, null);
  assert.equal(parsed.method_py, "");
  assert.equal(parsed.requirements, "");
  assert.deepEqual(parsed.method_config, {});

  const other = await setup();
  const s2 = await other.signIn();
  const unknown = await other.call("/api/submissions", post(s2, { ...reference, reference_method: "ledger" }));
  assert.equal(unknown.status, 400);
});

test("My runs lists only your own submissions, newest first, never cached", async () => {
  const { call, signIn, store } = await setup();
  assert.equal((await call("/api/me/submissions")).status, 401);
  const session = await signIn();
  assert.equal((await call("/api/submissions", post(session, form))).status, 201);
  const base = {
    handle: "bob", method_name: "other", method_version: "1.0.0", provider: "openai", model: "x",
    model_label: null, status: "published" as const, message: null, score: 0.5,
    created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
  };
  await store.insert({ ...base, id: "bobrun000001", github_id: 7 }, "{}");
  await store.insert({ ...base, id: "aliceold0001", github_id: 42, handle: "alice", method_name: "older" }, "{}");

  const response = await call("/api/me/submissions", { headers: { Cookie: session } });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  const body = (await response.json()) as { login: string; submissions: Record<string, unknown>[] };
  assert.equal(body.login, "alice");
  assert.deepEqual(body.submissions.map((s) => s.method_name), ["ledger", "older"]);
  assert.ok(body.submissions.every((s) => s.github_id === undefined), "no account ids in the response");
  assert.equal(body.submissions[1]!.status_url, "/status?id=aliceold0001");
});

test("sign-in can return to My runs, and nowhere outside the site", async () => {
  const { call } = await setup();
  const back = async (next: string) => {
    const start = await call(`/auth/github?next=${encodeURIComponent(next)}`);
    const stateCookie = start.headers.get("Set-Cookie")!.split(";")[0]!;
    const state = new URL(start.headers.get("Location")!).searchParams.get("state");
    return (await call(`/auth/callback?code=abc&state=${state}`, { headers: { Cookie: stateCookie } })).headers.get("Location");
  };
  assert.equal(await back("/runs"), "/runs");
  assert.equal(await back("https://evil.test/"), "/submit");
  assert.equal(await back("//evil.test"), "/submit");
});

test("without its secrets, sign-in says so instead of failing", async () => {
  const { call } = await setup({ SESSION_SECRET: "" });
  const response = await call("/auth/github");
  assert.equal(response.status, 503);
  assert.match(await response.text(), /isn't set up/);
});

test("a run that stops reporting is closed after the stale window, so its submitter can submit again", async () => {
  const store = new MemoryStore();
  const now = Date.parse("2026-11-17T12:00:00Z");
  const at = (ms: number) => new Date(now - ms).toISOString();
  const record = (id: string, status: SubmissionRecord["status"], updated: string): SubmissionRecord => ({
    id, github_id: 7, handle: "bob", method_name: "m", method_version: "1.0.0", provider: "anthropic",
    model: "claude-haiku-5-5", model_label: null, status, message: null, score: null,
    created_at: updated, updated_at: updated,
  });
  await store.insert(record("stuck", "running", at(STALE_AFTER_MS + 60_000)), "{}");
  await store.insert(record("busy", "running", at(STALE_AFTER_MS - 60_000)), "{}");
  await store.insert(record("done", "published", at(STALE_AFTER_MS * 3)), "{}");
  const closed = await store.expireStale(at(STALE_AFTER_MS), STALE_MESSAGE);
  assert.equal(closed, 1);
  assert.equal((await store.get("stuck"))?.status, "failed");
  assert.equal((await store.get("stuck"))?.message, STALE_MESSAGE);
  assert.equal((await store.get("busy"))?.status, "running", "a run inside the window is left alone");
  assert.equal((await store.get("done"))?.status, "published", "finished runs are never touched");
});
