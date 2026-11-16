import type { APIRoute, GetStaticPaths } from "astro";
import { docMarkdown, docs } from "../../lib/docs";

// Markdown twin of every doc: /docs/writing-a-compactor.md, …
export const getStaticPaths: GetStaticPaths = () => docs.map((doc) => ({ params: { slug: doc.slug } }));

export const GET: APIRoute = ({ params }) =>
  new Response(docMarkdown(params.slug as string), { headers: { "Content-Type": "text/markdown; charset=utf-8" } });
