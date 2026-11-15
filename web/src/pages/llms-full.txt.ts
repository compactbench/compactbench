import type { APIRoute } from "astro";
import { docMarkdown, docs } from "../lib/docs";
import { pages } from "../lib/markdown";

// Every page's and doc's Markdown in one file, for models that read a site in one go.
export const GET: APIRoute = () =>
  new Response(
    [...Object.values(pages).map((p) => p.body()), ...docs.map((d) => docMarkdown(d.slug))]
      .map((text) => text.trim())
      .join("\n\n---\n\n") + "\n",
    { headers: { "Content-Type": "text/plain; charset=utf-8" } },
  );
