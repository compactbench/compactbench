// Worker for compactbench.com. Static pages are served straight from assets; only
// the dynamic routes listed in wrangler.jsonc ("run_worker_first") reach this code.
import { type ApiEnv, handleApi } from "./api.ts";
import { EmailMessage } from "cloudflare:email";
import selftest from "../src/generated/selftest.json" with { type: "json" };
import { type Data, handleHttp } from "./mcp.ts";
import { buildDailyReport, dayOf, rawReport, type ReportEnv } from "./report.ts";
import type { SelfTestData } from "./selftest.ts";
import { secured } from "./security.ts";
import { CloudflareStore, D1ContactLog, D1StatsStore, type D1, type R2 } from "./store.ts";

interface Env extends ApiEnv, ReportEnv {
  ASSETS: { fetch: (request: Request | string) => Promise<Response> };
  DB: D1;
  BUNDLES: R2;
  /** Private: each finished ranked run's sealed traces and results. */
  ARCHIVE?: R2;
  /** Cloudflare Email Routing binding, added at launch (see LAUNCH.md). */
  SEND_EMAIL?: { send(message: EmailMessage): Promise<void> };
  REPORT_FROM?: string;
}

interface Ctx {
  waitUntil(promise: Promise<unknown>): void;
}

/** Which counter, if any, a finished request adds to. Totals only. */
function eventFor(request: Request, path: string, status: number): string | null {
  if (path === "/api/contact" && status === 200) return "contact";
  if (path === "/api/submissions" && request.method === "POST" && status === 201) return "submission";
  if (path === "/auth/callback" && status === 302) return "signin";
  if (path === "/api/me/submissions" && status === 200) return "my_runs";
  return null;
}

/** MCP counters: sessions and each tool called, read from the JSON-RPC body. */
async function mcpEvents(request: Request): Promise<string[]> {
  try {
    const body = (await request.clone().json()) as unknown;
    const messages = (Array.isArray(body) ? body : [body]) as { method?: string; params?: { name?: string } }[];
    return messages.flatMap((m) => {
      if (m?.method === "initialize") return ["mcp_session"];
      if (m?.method === "tools/call" && typeof m.params?.name === "string" && /^[a-z_]{1,40}$/.test(m.params.name)) {
        return [`mcp_tool:${m.params.name}`, ...(m.params.name === "selftest_score" ? ["selftest_score"] : [])];
      }
      return [];
    });
  } catch {
    return [];
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: Ctx): Promise<Response> {
    const url = new URL(request.url);
    const stats = new D1StatsStore(env.DB);
    const count = (events: string[]) => {
      const day = dayOf(new Date());
      // Never delay or fail a response over a counter.
      ctx.waitUntil(Promise.all(events.map((e) => stats.bump(day, e))).catch(() => undefined));
    };
    if (url.pathname === "/mcp") {
      if (request.method === "POST") count(await mcpEvents(request));
      const get = async (path: string) => (await env.ASSETS.fetch(new URL(path, url).toString())).json();
      const response = await handleHttp(request, async () => {
        const [leaderboard, families, season] = await Promise.all([
          get("/api/leaderboard.json"),
          get("/api/families.json"),
          get("/api/season.json"),
        ]);
        return {
          // Bundled with the Worker (scripts/selftest_cases.py), so it is parsed once per isolate.
          selftest: selftest as SelfTestData,
          rows: (leaderboard as { entries: Data["rows"] }).entries,
          families: (families as { families: Data["families"] }).families,
          season: season as Data["season"],
        };
      });
      return secured(response);
    }
    const mail = env.SEND_EMAIL;
    const api = await handleApi(request, env, {
      store: new CloudflareStore(env.DB, env.BUNDLES, env.ARCHIVE),
      contactLog: new D1ContactLog(env.DB),
      sendMail: mail ? (raw, from, to) => mail.send(new EmailMessage(from, to, raw)) : undefined,
    });
    if (api) {
      const event = eventFor(request, url.pathname, api.status);
      if (event) count([event]);
      return secured(api);
    }
    // Assets keep their own Content-Security-Policy from public/_headers.
    return secured(await env.ASSETS.fetch(request), false);
  },

  /** The owner's daily report (cron in wrangler.jsonc). Needs email set up, like the contact form. */
  async scheduled(_controller: unknown, env: Env, ctx: Ctx): Promise<void> {
    const mail = env.SEND_EMAIL;
    const from = env.REPORT_FROM ?? env.CONTACT_FROM;
    if (!mail || !env.CONTACT_TO || !from) return;
    const now = new Date();
    ctx.waitUntil(
      (async () => {
        const report = await buildDailyReport(env, new D1StatsStore(env.DB), now, fetch);
        const raw = rawReport(report, { from, to: env.CONTACT_TO!, id: crypto.randomUUID(), now, host: "compactbench.com" });
        await mail.send(new EmailMessage(from, env.CONTACT_TO!, raw));
      })(),
    );
  },
};
