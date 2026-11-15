import type { APIRoute } from "astro";
import { pct, type Row, rows, seasonLabel, slugOf } from "../../../lib/data";

// A shields.io endpoint badge per leaderboard row, for READMEs:
// https://img.shields.io/endpoint?url=https://compactbench.com/api/badges/<slug>.json
export function getStaticPaths() {
  return rows.map((row) => ({ params: { slug: slugOf(row) }, props: { row } }));
}

export const GET: APIRoute = ({ props }) => {
  const row = props.row as Row;
  return new Response(
    JSON.stringify({
      schemaVersion: 1,
      label: `CompactBench ${seasonLabel(row.season)}`,
      message: `${pct(row.score)} (${pct(row.score_ci_low)}–${pct(row.score_ci_high)})`,
      color: "3b82f6",
      labelColor: "05060b",
    }),
    { headers: { "Content-Type": "application/json; charset=utf-8" } },
  );
};
