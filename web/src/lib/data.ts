// Data the site renders, produced by scripts/export_site_data.py from the package.
import calibrationJson from "../generated/calibration.json";
import familiesJson from "../generated/families.json";
import leaderboardJson from "../generated/leaderboard.json";
import seasonJson from "../generated/season.json";
import suitesJson from "../generated/suites.json";

export interface Family {
  key: string;
  title: string;
  version: string;
  description: string;
}

export interface Suite {
  key: string;
  version: string;
  description: string;
  difficulty: string;
  families: string[];
  cases: number;
  opening_tokens: number;
  drift_cycles: number;
}

/** One leaderboard row. Mirrors compactbench.leaderboard.projection.LeaderboardRow. */
export interface Row {
  slug: string;
  rank: number | null;
  row_kind: "submission" | "baseline" | "control";
  method_name: string;
  method_version: string;
  handle: string | null;
  org: string | null;
  suite: string;
  season: string | null;
  scorer_version: string;
  reader_provider: string;
  reader_model: string;
  reader_effort: string | null;
  compactor_provider: string;
  compactor_model: string;
  compactor_endpoint_kind?: string;
  /** Display name a submitter gave their own custom-endpoint model. */
  model_label?: string | null;
  budget_tokens: number | null;
  score: number;
  score_ci_low: number;
  score_ci_high: number;
  normalized_score: number | null;
  drift_resistance: number;
  stale_rate: number;
  trap_rate: number;
  hallucination_rate: number;
  mean_artifact_tokens: number;
  compression_ratio: number;
  method_tokens: number | null;
  by_family: Record<string, number>;
  by_cycle: number[];
  cases: number;
  published_at: string;
}

export interface Calibration {
  season: string;
  suite: string;
  reader: string;
  cases: number;
  measured_at: string;
  families: Record<string, { ceiling: number; floor: number }>;
}

/** The season's measured ceiling and floor per family, once calibrated. */
export const calibration = calibrationJson as Calibration | null;
export const families: Family[] = familiesJson;
export const suites: Suite[] = suitesJson;
export const season = seasonJson;
export const rows: Row[] = (leaderboardJson as { entries: Row[] }).entries;
export const updatedAt: string = (leaderboardJson as { updated_at: string }).updated_at;

export const pct = (value: number | null | undefined, digits = 1): string =>
  value === null || value === undefined ? "—" : `${(value * 100).toFixed(digits)}`;

export const familyTitle = (key: string): string =>
  families.find((f) => f.key === key)?.title ?? key;

/** Rows in display order: ranked submissions first, then baselines, then controls. */
export function ordered(list: Row[]): Row[] {
  const kind = { submission: 0, baseline: 1, control: 2 } as const;
  return [...list].sort(
    (a, b) => kind[a.row_kind] - kind[b.row_kind] || b.score - a.score,
  );
}

/** URL slug for a row, set by scripts/export_site_data.py (submitter, method, version, model, season). */
export const slugOf = (row: Row): string => row.slug;

/** The model as shown: a custom endpoint's display name, else the model id. */
export const modelName = (row: Row): string => row.model_label || row.compactor_model;
export const isCustomEndpoint = (row: Row): boolean => row.compactor_endpoint_kind === "custom";
