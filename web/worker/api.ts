// The site's dynamic routes: GitHub sign-in, ranked submissions and their status, and
// the internal endpoints the evaluation workflow calls.
import { contact, ContactError, type ContactInput, type ContactLog, type SendMail } from "./contact.ts";
import { authorizeUrl, isEvaluationWorkflow, userFromCode } from "./github.ts";
import { cookie, readCookie, signValue, verifyValue } from "./session.ts";
import type { Status, Store } from "./store.ts";
import { publicView, REPORTABLE, submit, SubmitError, type SubmitInput } from "./submissions.ts";

export interface ApiEnv {
  GITHUB_CLIENT_ID: string;
  GITHUB_CLIENT_SECRET: string;
  SESSION_SECRET: string;
  SEASON_KEY: string;
  SEASON_PUBLIC_KEY: string;
  GITHUB_REPO: string;
  GITHUB_DISPATCH_TOKEN: string;
  OIDC_AUDIENCE: string;
  SUBMISSIONS_OPEN?: string;
  /** GitHub logins (comma-separated) that may submit while SUBMISSIONS_OPEN is "false", e.g. for a smoke test. */
  SUBMISSIONS_EARLY_ACCESS?: string;
  LIMIT_PER_WEEK?: string;
  LIMIT_PER_DAY?: string;
  TURNSTILE_SECRET?: string;
  /** Contact form: the maintainer's address (a secret) and the sending address on our domain. */
  CONTACT_TO?: string;
  CONTACT_FROM?: string;
}

export interface Deps {
  store: Store;
  fetcher?: typeof fetch;
  /** Present once email sending is configured; without it the contact form says so. */
  sendMail?: SendMail;
  contactLog?: ContactLog;
}

const SESSION = "cb_session";
/** A finished run's files the evaluation keeps privately; nothing else is accepted. */
export const ARCHIVE_FILES = new Set([
  "results.sealed", "traces.sealed", "calls.sealed", "commitment.json", "submission.json", "results.jsonl",
]);
/** Under the Workers request-body limit. */
const MAX_ARCHIVE_BYTES = 95_000_000;
const STATE = "cb_oauth_state";
const json = (body: unknown, status = 200) =>
  Response.json(body, { status, headers: { "Cache-Control": "no-store" } });

/** Pages a sign-in may return to. A fixed list, so the link can't redirect anywhere else. */
const RETURN_TO = new Set(["/submit", "/runs"]);

export async function sessionUser(request: Request, env: ApiEnv) {
  return verifyValue<{ login: string; id: number }>(env.SESSION_SECRET, readCookie(request, SESSION));
}

/** Returns a response for the routes this module owns, or null to fall through. */
export async function handleApi(request: Request, env: ApiEnv, deps: Deps): Promise<Response | null> {
  const url = new URL(request.url);
  const path = url.pathname;
  const fetcher = deps.fetcher ?? fetch;

  if (path === "/auth/github" && request.method === "GET") {
    if (!env.SESSION_SECRET || !env.GITHUB_CLIENT_ID || env.GITHUB_CLIENT_ID.startsWith("REPLACE_")) {
      return new Response("Sign-in isn't set up on this server yet.", { status: 503 });
    }
    const state = crypto.randomUUID();
    const redirect = new URL("/auth/callback", url.origin).toString();
    const next = url.searchParams.get("next") ?? "";
    const returnTo = RETURN_TO.has(next) ? next : "/submit";
    return new Response(null, {
      status: 302,
      headers: {
        Location: authorizeUrl(env.GITHUB_CLIENT_ID, redirect, state),
        "Set-Cookie": cookie(STATE, await signValue(env.SESSION_SECRET, { state, returnTo }, 600), 600),
      },
    });
  }

  if (path === "/auth/callback" && request.method === "GET") {
    const expected = await verifyValue<{ state: string; returnTo?: string }>(env.SESSION_SECRET, readCookie(request, STATE));
    const code = url.searchParams.get("code");
    if (!expected || !code || url.searchParams.get("state") !== expected.state) {
      return new Response("Sign-in expired or was tampered with. Please try again.", { status: 400 });
    }
    const user = await userFromCode(code, env.GITHUB_CLIENT_ID, env.GITHUB_CLIENT_SECRET, fetcher);
    if (!user) return new Response("GitHub sign-in failed. Please try again.", { status: 400 });
    const returnTo = expected?.returnTo && RETURN_TO.has(expected.returnTo) ? expected.returnTo : "/submit";
    const headers = new Headers({ Location: returnTo });
    headers.append("Set-Cookie", cookie(SESSION, await signValue(env.SESSION_SECRET, { ...user }, 8 * 3600), 8 * 3600));
    headers.append("Set-Cookie", cookie(STATE, "", 0));
    return new Response(null, { status: 302, headers });
  }

  if (path === "/auth/logout" && request.method === "POST") {
    return new Response(null, { status: 204, headers: { "Set-Cookie": cookie(SESSION, "", 0) } });
  }

  if (path === "/api/me" && request.method === "GET") {
    const user = await sessionUser(request, env);
    return user ? json({ login: user.login }) : json({ error: "signed out" }, 401);
  }

  if (path === "/api/contact" && request.method === "POST") {
    if (request.headers.get("Origin") !== url.origin) return json({ error: "cross-site request refused" }, 403);
    if (!deps.sendMail || !deps.contactLog || !env.CONTACT_TO || !env.CONTACT_FROM || !env.SESSION_SECRET) {
      return json({ error: "The contact form isn't set up yet. Please open an issue on GitHub instead." }, 503);
    }
    let body: ContactInput;
    try {
      body = (await request.json()) as ContactInput;
    } catch {
      return json({ error: "expected a JSON body" }, 400);
    }
    if (env.TURNSTILE_SECRET && !(await turnstileOk(env.TURNSTILE_SECRET, body.turnstile_token, request, fetcher))) {
      return json({ error: "Bot check failed; please retry." }, 403);
    }
    try {
      await contact(body, {
        log: deps.contactLog,
        send: deps.sendMail,
        from: env.CONTACT_FROM,
        to: env.CONTACT_TO,
        secret: env.SESSION_SECRET,
        ip: request.headers.get("CF-Connecting-IP") ?? "unknown",
        host: url.hostname,
      });
      return json({ ok: true });
    } catch (error) {
      if (error instanceof ContactError) return json({ error: error.message }, error.status);
      throw error;
    }
  }

  if (path === "/api/me/submissions" && request.method === "GET") {
    const user = await sessionUser(request, env);
    if (!user) return json({ error: "signed out" }, 401);
    const records = await deps.store.listForUser(user.id, 100);
    return json({
      login: user.login,
      submissions: records.map((r) => ({ ...publicView(r), status_url: `/status?id=${r.id}` })),
    });
  }

  if (path === "/api/submissions" && request.method === "POST") {
    // Same-origin only: the session cookie is SameSite=Lax, and this checks the rest.
    if (request.headers.get("Origin") !== url.origin) return json({ error: "cross-site request refused" }, 403);
    const user = await sessionUser(request, env);
    if (!user) return json({ error: "Sign in with GitHub to submit." }, 401);
    let body: SubmitInput & { turnstile_token?: unknown };
    try {
      body = (await request.json()) as SubmitInput & { turnstile_token?: unknown };
    } catch {
      return json({ error: "expected a JSON body" }, 400);
    }
    if (env.TURNSTILE_SECRET && !(await turnstileOk(env.TURNSTILE_SECRET, body.turnstile_token, request, fetcher))) {
      return json({ error: "Bot check failed; please retry." }, 403);
    }
    try {
      const record = await submit(body, {
        store: deps.store,
        limits: {
          open: env.SUBMISSIONS_OPEN !== "false" || earlyAccess(env.SUBMISSIONS_EARLY_ACCESS, user.login),
          perUserPerWeek: Number(env.LIMIT_PER_WEEK ?? 5),
          globalPerDay: Number(env.LIMIT_PER_DAY ?? 50),
        },
        season: env.SEASON_KEY,
        seasonPublicKey: env.SEASON_PUBLIC_KEY,
        user,
        dispatch: (id) => dispatch(env, id, fetcher),
      });
      return json({ id: record.id, status: record.status, status_url: `/status?id=${record.id}` }, 201);
    } catch (error) {
      if (error instanceof SubmitError) return json({ error: error.message }, error.status);
      throw error;
    }
  }

  const statusMatch = path.match(/^\/api\/submissions\/([a-z0-9]{12,32})$/);
  if (statusMatch && request.method === "GET") {
    const record = await deps.store.get(statusMatch[1] as string);
    return record ? json(publicView(record)) : json({ error: "not found" }, 404);
  }

  const internal = path.match(/^\/api\/internal\/(bundles|submissions)\/([a-z0-9]{12,32})$/);
  if (internal) {
    const token = (request.headers.get("Authorization") ?? "").replace(/^Bearer /, "") || null;
    if (!(await isEvaluationWorkflow(token, env.GITHUB_REPO, env.OIDC_AUDIENCE, fetcher))) {
      return json({ error: "forbidden" }, 403);
    }
    const id = internal[2] as string;
    if (internal[1] === "bundles" && request.method === "GET") {
      const bundle = await deps.store.getBundle(id);
      return bundle ? new Response(bundle, { headers: { "Content-Type": "application/json" } }) : json({ error: "not found" }, 404);
    }
    if (internal[1] === "submissions" && request.method === "POST") {
      const update = (await request.json()) as { status?: unknown; message?: unknown; score?: unknown };
      if (!REPORTABLE.includes(update.status as Status)) return json({ error: "bad status" }, 400);
      await deps.store.update(id, {
        status: update.status as Status,
        message: typeof update.message === "string" ? update.message.slice(0, 500) : undefined,
        score: typeof update.score === "number" && update.score >= 0 && update.score <= 1 ? update.score : undefined,
      });
      return json({ ok: true });
    }
  }

  const archive = path.match(/^\/api\/internal\/archive\/([a-z0-9]{12,32})\/([A-Za-z0-9._-]{1,64})$/);
  if (archive && request.method === "PUT") {
    const token = (request.headers.get("Authorization") ?? "").replace(/^Bearer /, "") || null;
    if (!(await isEvaluationWorkflow(token, env.GITHUB_REPO, env.OIDC_AUDIENCE, fetcher))) {
      return json({ error: "forbidden" }, 403);
    }
    const id = archive[1] as string;
    const name = archive[2] as string;
    if (!ARCHIVE_FILES.has(name)) return json({ error: "not an archived file" }, 400);
    if (!(await deps.store.get(id))) return json({ error: "not found" }, 404);
    if (Number(request.headers.get("Content-Length") ?? 0) > MAX_ARCHIVE_BYTES) return json({ error: "too large" }, 413);
    const body = await request.arrayBuffer();
    if (body.byteLength === 0) return json({ error: "empty" }, 400);
    if (body.byteLength > MAX_ARCHIVE_BYTES) return json({ error: "too large" }, 413);
    await deps.store.archive(env.SEASON_KEY, id, name, body);
    return json({ ok: true, bytes: body.byteLength });
  }
  return null;
}

/** Whether a login is on the early-access list (GitHub logins are case-insensitive). */
function earlyAccess(list: string | undefined, login: string): boolean {
  const wanted = login.toLowerCase();
  return (list ?? "").split(",").some((entry) => entry.trim().toLowerCase() === wanted && wanted !== "");
}

async function dispatch(env: ApiEnv, id: string, fetcher: typeof fetch): Promise<boolean> {
  const response = await fetcher(
    `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/evaluate-submission.yml/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "compactbench",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: "main", inputs: { submission_id: id } }),
    },
  );
  if (response.status === 204) return true;
  // The status only (never the body or the token): enough to tell an expired token from an outage.
  console.error(`workflow dispatch failed: HTTP ${response.status}`);
  return false;
}

async function turnstileOk(secret: string, token: unknown, request: Request, fetcher: typeof fetch): Promise<boolean> {
  if (typeof token !== "string" || !token) return false;
  const form = new FormData();
  form.set("secret", secret);
  form.set("response", token);
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) form.set("remoteip", ip);
  const response = await fetcher("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
  return ((await response.json()) as { success?: boolean }).success === true;
}

export { SubmitError };
