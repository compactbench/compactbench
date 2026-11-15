import type { APIRoute } from "astro";
import { type Row, rows, slugOf } from "../../../lib/data";

// One leaderboard row by slug — the same data as /methods/<slug>.
export function getStaticPaths() {
  return rows.map((row) => ({ params: { slug: slugOf(row) }, props: { row } }));
}

export const GET: APIRoute = ({ props, params }) =>
  new Response(JSON.stringify({ ...(props.row as Row), url: `https://compactbench.com/methods/${params.slug}` }), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
