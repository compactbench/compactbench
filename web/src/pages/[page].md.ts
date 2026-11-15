import type { APIRoute, GetStaticPaths } from "astro";
import { pages } from "../lib/markdown";

// A Markdown twin of every content page: /methodology.md, /leaderboard.md, …
export const getStaticPaths: GetStaticPaths = () =>
  Object.keys(pages).map((page) => ({ params: { page } }));

export const GET: APIRoute = ({ params }) =>
  new Response(pages[params.page as string].body(), {
    headers: { "Content-Type": "text/markdown; charset=utf-8" },
  });
