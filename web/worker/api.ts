// The site's dynamic routes: GitHub sign-in, ranked submissions and their status, and
// the two internal endpoints the evaluation workflow calls.
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
  LIMIT_PER_WEEK?: string;
  LIMIT_PER_DAY?: string;
  TURNSTILE_SECRET?: string;
}

export interface Deps {
  store: Store;
  fetcher?: typeof fetch;
}

const SESSION = "cb_session";
const STATE = "cb_oauth_state";
const json = (body: unknown, status = 200) =>
  Response.json(body, { status, headers: { "Cache-Control": "no-store" } });

export async function sessionUser(request: Request, env: ApiEnv) {
  return verifyValue<{ login: string; id: number }>(env.SESSION_SECRET, readCookie(request, SESSION));
}

/** Returns a response for the routes this module owns, or null to fall through. */
export async function handleApi(request: Request, env: ApiEnv, deps: Deps): Promise<Response | null> {
  const url = new URL(request.url);
  const path = url.pathname;
  const fetcher = deps.fetcher ?? fetch;

  if (path === "/auth/github" && request.method === "GET") {
    const state = crypto.randomUUID();
    const redirect = new URL("/auth/callback", url.origin).toString();
    return new Response(null, {
      status: 302,
      headers: {
        Location: authorizeUrl(env.GITHUB_CLIENT_ID, redirect, state),
        "Set-Cookie": cookie(STATE, await signValue(env.SESSION_SECRET, { state }, 600), 600),
      },
    });
  }

  if (path === "/auth/callback" && request.method === "GET") {
    const expected = await verifyValue<{ state: string }>(env.SESSION_SECRET, readCookie(request, STATE));
    const code = url.searchParams.get("code");
    if (!expected || !code || url.searchParams.get("state") !== expected.state) {
      return new Response("Sign-in expired or was tampered with. Please try again.", { status: 400 });
    }
    const user = await userFromCode(code, env.GITHUB_CLIENT_ID, env.GITHUB_CLIENT_SECRET, fetcher);
    if (!user) return new Response("GitHub sign-in failed. Please try again.", { status: 400 });
    const headers = new Headers({ Location: "/submit" });
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
          open: env.SUBMISSIONS_OPEN !== "false",
          perUserPerWeek: Number(env.LIMIT_PER_WEEK ?? 2),
          globalPerDay: Number(env.LIMIT_PER_DAY ?? 20),
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
  return null;
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
  return response.status === 204;
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
