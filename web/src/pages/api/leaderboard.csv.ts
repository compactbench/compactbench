import type { APIRoute } from "astro";
import { toCsv } from "../../lib/csv";
import { families, modelName, ordered, rows, slugOf } from "../../lib/data";

// The leaderboard as one CSV row per published row, per-family scores as columns.
export const GET: APIRoute = () => {
  const familyKeys = families.map((f) => f.key);
  const header = [
    "rank", "kind", "method", "version", "handle", "org", "model", "provider", "endpoint",
    "score", "ci_low", "ci_high", "normalized_score", "drift_resistance", "stale_rate",
    "trap_rate", "hallucination_rate", "artifact_tokens", "method_tokens", "cases",
    "budget_tokens", "season", "suite", "reader", "reader_effort", "scorer", "published_at",
    ...familyKeys.map((k) => `family_${k}`), "url",
  ];
  const body = ordered(rows).map((r) => [
    r.rank, r.row_kind, r.method_name, r.method_version, r.handle, r.org, modelName(r),
    r.compactor_provider, r.compactor_endpoint_kind ?? "hosted", r.score, r.score_ci_low,
    r.score_ci_high, r.normalized_score, r.drift_resistance, r.stale_rate, r.trap_rate,
    r.hallucination_rate, r.mean_artifact_tokens, r.method_tokens, r.cases, r.budget_tokens,
    r.season, r.suite, r.reader_model, r.reader_effort, r.scorer_version, r.published_at,
    ...familyKeys.map((k) => r.by_family[k] ?? null), `https://compactbench.com/methods/${slugOf(r)}`,
  ]);
  return new Response(toCsv(header, body), {
    headers: { "Content-Type": "text/csv; charset=utf-8" },
  });
};
