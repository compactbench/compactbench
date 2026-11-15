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
  /** Set when the row ran a reference method unchanged on its model (the By model board). */
  reference_method?: string | null;
  /** Rank among models on the same reference method; `rank` is the method board's. */
  model_rank?: number | null;
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

/** "s1" → "Season 1"; any other key is shown as is. */
export const seasonLabel = (key: string | null | undefined): string => {
  if (!key) return "—";
  const m = /^s(\d+)$/i.exec(key);
  return m ? `Season ${m[1]}` : key;
};

/**
 * Score as a share of what's achievable: per family, (score − floor) / (ceiling − floor)
 * from the season's calibration, averaged over families. Null without a calibration for
 * the row's season.
 */
export function normalizedScore(row: Row): number | null {
  if (row.normalized_score !== null) return row.normalized_score;
  if (!calibration || calibration.season !== row.season) return null;
  const shares = Object.entries(row.by_family).flatMap(([family, score]) => {
    const band = calibration?.families[family];
    if (!band || band.ceiling <= band.floor) return [];
    return [Math.min(1, Math.max(0, (score - band.floor) / (band.ceiling - band.floor)))];
  });
  return shares.length ? shares.reduce((a, b) => a + b, 0) / shares.length : null;
}

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

/** Built-ins anyone can run on their own model, in board order, with display titles. */
export const referenceMethods: { key: string; title: string }[] = [
  { key: "sectioned-summary", title: "Sectioned summary" },
  { key: "hierarchical-summary", title: "Hierarchical summary" },
  { key: "naive-summary", title: "Plain summary" },
  { key: "structured-state", title: "Structured state" },
];

/** A submitted model row (not a maintainer baseline) that ran a reference method. */
export const isModelRow = (row: Row): boolean => row.row_kind === "submission" && !!row.reference_method;

export interface ModelLine {
  model: string;
  provider: string;
  custom: boolean;
  by: string;
  cells: Record<string, Row>;
}

/** The By model board: one line per model (and submitter), one cell per reference method,
 * ordered by the first method's score. */
export function byModel(list: Row[]): ModelLine[] {
  const lines = new Map<string, ModelLine>();
  for (const row of list) {
    if (!row.reference_method) continue;
    const by = row.handle ? `@${row.handle}` : (row.org ?? "");
    const key = [row.compactor_provider, row.compactor_model, row.model_label ?? "", by].join("|");
    const line = lines.get(key) ?? {
      model: modelName(row),
      provider: row.compactor_provider,
      custom: isCustomEndpoint(row),
      by,
      cells: {},
    };
    const held = line.cells[row.reference_method];
    if (!held || row.published_at > held.published_at) line.cells[row.reference_method] = row;
    lines.set(key, line);
  }
  const best = (line: ModelLine) =>
    referenceMethods.map((m) => line.cells[m.key]?.score ?? -1).find((score) => score >= 0) ?? -1;
  const order = (line: ModelLine) => referenceMethods.findIndex((m) => line.cells[m.key]);
  return [...lines.values()].sort((a, b) => order(a) - order(b) || best(b) - best(a));
}
