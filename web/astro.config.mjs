import sitemap from "@astrojs/sitemap";
import { defineConfig } from "astro/config";

// Static site: every page renders without JavaScript; small scripts only enhance
// (table sorting, filters, the submit form). Scripts are always emitted as files, never
// inlined, so the Content-Security-Policy in public/_headers can stay script-src 'self'.
export default defineConfig({
  site: "https://compactbench.com",
  trailingSlash: "never",
  build: { format: "file" },
  vite: { build: { assetsInlineLimit: 0 } },
  integrations: [sitemap()],
});
