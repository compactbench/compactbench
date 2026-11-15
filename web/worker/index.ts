// Worker for compactbench.com. Static pages are served straight from assets; only
// the dynamic routes listed in wrangler.jsonc ("run_worker_first") reach this code.
import { type ApiEnv, handleApi } from "./api.ts";
import { type Data, handleHttp } from "./mcp.ts";
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
      return handleHttp(request, async () => {
        const [leaderboard, families, season] = await Promise.all([
          get("/api/leaderboard.json"),
          get("/api/families.json"),
          get("/api/season.json"),
        ]);
        return {
          rows: (leaderboard as { entries: Data["rows"] }).entries,
          families: (families as { families: Data["families"] }).families,
          season: season as Data["season"],
        };
      });
    }
    const api = await handleApi(request, env, { store: new CloudflareStore(env.DB, env.BUNDLES) });
    return api ?? env.ASSETS.fetch(request);
  },
};
