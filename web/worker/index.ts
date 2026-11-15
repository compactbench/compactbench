// Worker for compactbench.com. Static pages are served straight from assets; only
// the dynamic routes listed in wrangler.jsonc ("run_worker_first") reach this code.
import { type ApiEnv, handleApi } from "./api.ts";
import selftest from "../src/generated/selftest.json" with { type: "json" };
import { type Data, handleHttp } from "./mcp.ts";
import type { SelfTestData } from "./selftest.ts";
import { secured } from "./security.ts";
import { CloudflareStore, type D1, type R2 } from "./store.ts";

interface Env extends ApiEnv {
  ASSETS: { fetch: (request: Request | string) => Promise<Response> };
  DB: D1;
  BUNDLES: R2;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/mcp") {
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
    const api = await handleApi(request, env, { store: new CloudflareStore(env.DB, env.BUNDLES) });
    // Assets keep their own Content-Security-Policy from public/_headers.
    return api ? secured(api) : secured(await env.ASSETS.fetch(request), false);
  },
};
