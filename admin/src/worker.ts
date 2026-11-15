// admin.compactbench.com — the owner's dashboard. Read-only: website submissions
// (from the site's D1 database), ranked evaluation runs (GitHub Actions) and the
// published leaderboard.
import { type AccessConfig, verifyAccess } from "./access.ts";

/** The slice of D1 this dashboard uses. */
export interface D1 {
  prepare(sql: string): { bind(...values: unknown[]): { all<T>(): Promise<{ results: T[] }> } };
}

export interface Env {
  ACCESS_TEAM_DOMAIN: string;
  ACCESS_AUD: string;
  OWNER_EMAIL: string;
  GITHUB_REPO: string; // "compactbench/compactbench"
  GITHUB_TOKEN?: string; // fine-grained, read-only: actions
  SITE_URL: string; // "https://compactbench.com"
  DB?: D1; // the site's submissions database
}

interface Submission {
  id: string;
  handle: string;
  method_name: string;
  method_version: string;
  provider: string;
  model: string;
  model_label: string | null;
  status: string;
  message: string | null;
  score: number | null;
  created_at: string;
  updated_at: string;
}

const ACTIVE = ["queued", "building", "running"];
const STUCK_HOURS = 4;

interface WorkflowRun {
  id: number;
  html_url: string;
  status: string;
  conclusion: string | null;
  created_at: string;
  run_started_at?: string;
  updated_at: string;
  head_branch: string;
  pull_requests?: { number: number }[];
  display_title?: string;
}

export interface Row {
  method_name: string;
  method_version: string;
  row_kind: string;
  handle?: string | null;
  compactor_model: string;
  score: number;
  score_ci_low: number;
  score_ci_high: number;
  by_family?: Record<string, number>;
  season: string | null;
  published_at: string;
}

export interface FamilyStat {
  family: string;
  best: number;
  best_method: string;
  median: number;
  rows: number;
}

export interface Flag {
  method: string;
  reason: string;
}

export interface Summary {
  submissions: (Submission & { stuck: boolean })[];
  counts: { day: number; week: number; active: number; failed_week: number };
  runs: { id: number; url: string; title: string; status: string; conclusion: string | null; started: string; minutes: number }[];
  leaderboard: Row[];
  families: FamilyStat[];
  flags: Flag[];
  errors: string[];
}

/** Per family across published rows (controls excluded): best score, who, and the median. */
export function familyDifficulty(rows: Row[]): FamilyStat[] {
  const by: Record<string, { score: number; method: string }[]> = {};
  for (const r of rows) {
    if (r.row_kind === "control") continue;
    for (const [family, score] of Object.entries(r.by_family ?? {})) {
      (by[family] ??= []).push({ score, method: r.handle ? `@${r.handle}/${r.method_name}` : r.method_name });
    }
  }
  return Object.entries(by)
    .map(([family, list]) => {
      const sorted = [...list].sort((a, b) => b.score - a.score);
      const mid = sorted.length >> 1;
      const median = sorted.length % 2 ? sorted[mid]!.score : (sorted[mid - 1]!.score + sorted[mid]!.score) / 2;
      return { family, best: sorted[0]!.score, best_method: sorted[0]!.method, median, rows: sorted.length };
    })
    .sort((a, b) => a.best - b.best);
}

/**
 * Published submissions worth a look against their sealed traces: a family far above the
 * method's overall score (a sign of fingerprinting one family), or a large lead over every
 * baseline. Flags are prompts for review, not verdicts.
 */
export function flagRows(rows: Row[]): Flag[] {
  const baselines = rows.filter((r) => r.row_kind === "baseline").map((r) => r.score);
  const bestBaseline = baselines.length ? Math.max(...baselines) : null;
  const flags: Flag[] = [];
  for (const r of rows) {
    if (r.row_kind !== "submission") continue;
    const method = `@${r.handle ?? "?"}/${r.method_name} ${r.method_version}`;
    for (const [family, score] of Object.entries(r.by_family ?? {})) {
      if (score >= 0.85 && score - r.score >= 0.35) {
        flags.push({ method, reason: `${family} at ${(score * 100).toFixed(0)} vs ${(r.score * 100).toFixed(0)} overall` });
      }
    }
    if (bestBaseline !== null && r.score - bestBaseline >= 0.2) {
      flags.push({ method, reason: `leads the best baseline by ${((r.score - bestBaseline) * 100).toFixed(0)} points` });
    }
  }
  return flags;
}

const FORMULA = /^[=+\-@\t\r]/;

/** CSV cell, guarded against spreadsheet formulas (submitter text starts with = + - @). */
export function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (typeof value !== "number" && FORMULA.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

const EXPORT_COLUMNS = [
  "id", "handle", "method_name", "method_version", "provider", "model", "model_label",
  "status", "message", "score", "created_at", "updated_at",
] as const;

/** Every submission (no keys or code live in D1), as CSV. */
export async function exportSubmissions(db: D1): Promise<string> {
  const { results } = await db.prepare("SELECT * FROM submissions ORDER BY created_at DESC LIMIT ?").bind(50_000).all<Submission>();
  const lines = [EXPORT_COLUMNS.join(","), ...results.map((s) => EXPORT_COLUMNS.map((c) => csvCell(s[c])).join(","))];
  return lines.join("\r\n") + "\r\n";
}

export async function summarize(env: Env, fetcher: typeof fetch = fetch, now = Date.now()): Promise<Summary> {
  const errors: string[] = [];
  const gh = async <T>(path: string): Promise<T | null> => {
    const headers: Record<string, string> = {
      Accept: "application/vnd.github+json",
      "User-Agent": "compactbench-admin",
      "X-GitHub-Api-Version": "2022-11-28",
    };
    if (env.GITHUB_TOKEN) headers.Authorization = `Bearer ${env.GITHUB_TOKEN}`;
    const response = await fetcher(`https://api.github.com/repos/${env.GITHUB_REPO}${path}`, { headers });
    if (!response.ok) {
      errors.push(`GitHub ${path}: ${response.status}`);
      return null;
    }
    return (await response.json()) as T;
  };

  const recent = async (): Promise<Submission[] | null> => {
    if (!env.DB) {
      errors.push("No submissions database bound");
      return null;
    }
    try {
      const since = new Date(now - 7 * 86_400_000).toISOString();
      const { results } = await env.DB.prepare(
        "SELECT * FROM submissions WHERE created_at >= ? OR status IN ('queued', 'building', 'running') ORDER BY created_at DESC LIMIT 100",
      )
        .bind(since)
        .all<Submission>();
      return results;
    } catch (error) {
      errors.push(`Submissions database: ${String(error)}`);
      return null;
    }
  };

  const [submissions, runs, board] = await Promise.all([
    recent(),
    gh<{ workflow_runs: WorkflowRun[] }>("/actions/workflows/evaluate-submission.yml/runs?per_page=20"),
    fetcher(new URL("/api/leaderboard.json", env.SITE_URL).toString())
      .then(async (r) => (r.ok ? ((await r.json()) as { entries: Row[] }) : null))
      .catch(() => null),
  ]);
  if (!board) errors.push("leaderboard.json unavailable");

  const rows = (submissions ?? []).map((s) => ({
    ...s,
    stuck: ACTIVE.includes(s.status) && now - Date.parse(s.updated_at) > STUCK_HOURS * 3_600_000,
  }));
  const since = (days: number) => rows.filter((s) => now - Date.parse(s.created_at) <= days * 86_400_000);
  const counts = {
    day: since(1).length,
    week: since(7).length,
    active: rows.filter((s) => ACTIVE.includes(s.status)).length,
    failed_week: since(7).filter((s) => s.status === "failed").length,
  };
  const minutes = (r: WorkflowRun) =>
    Math.max(0, Math.round((Date.parse(r.updated_at) - Date.parse(r.run_started_at ?? r.created_at)) / 60000));
  return {
    submissions: rows,
    counts,
    runs: (runs?.workflow_runs ?? []).map((r) => ({
      id: r.id,
      url: r.html_url,
      title: r.display_title ?? r.head_branch,
      status: r.status,
      conclusion: r.conclusion,
      started: r.run_started_at ?? r.created_at,
      minutes: minutes(r),
    })),
    leaderboard: board?.entries ?? [],
    families: familyDifficulty(board?.entries ?? []),
    flags: flagRows(board?.entries ?? []),
    errors,
  };
}

const esc = (text: unknown): string =>
  String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);

const statusClass = (s: { status: string; stuck: boolean }) =>
  s.stuck || s.status === "failed" ? "bad" : s.status === "published" ? "good" : ACTIVE.includes(s.status) ? "warn" : "muted";

export function render(summary: Summary, email: string, siteUrl = "https://compactbench.com"): string {
  const pct = (v: number) => (v * 100).toFixed(1);
  const table = (head: string[], rows: string[][]) =>
    `<table><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${
      rows.length ? rows.map((r) => `<tr>${r.join("")}</tr>`).join("") : `<tr><td colspan="${head.length}" class="muted">Nothing here.</td></tr>`
    }</tbody></table>`;
  const td = (v: unknown, cls = "") => `<td class="${cls}">${esc(v)}</td>`;
  const link = (url: string, text: unknown) =>
    /^https:\/\//.test(url) ? `<td><a href="${esc(url)}">${esc(text)}</a></td>` : `<td>${esc(text)}</td>`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>CompactBench admin</title><style>
body{margin:0;background:#05060b;color:#e6eaf2;font:15px/1.55 system-ui,sans-serif}main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.05rem;margin:32px 0 10px;color:#8a93a6;text-transform:uppercase;letter-spacing:.08em}
table{width:100%;border-collapse:collapse;background:#0b0e17;border:1px solid #1a2133;border-radius:10px;overflow:hidden;font-size:.9rem}
th,td{padding:.55em .7em;border-bottom:1px solid #1a2133;text-align:left}th{color:#8a93a6;font-size:.75rem;text-transform:uppercase}
a{color:#22d3ee}.muted{color:#8a93a6}.mono{font-family:ui-monospace,monospace}.bad{color:#f87171}.good{color:#34d399}.warn{color:#fbbf24}
.errors{background:#1f1214;border:1px solid #5b2a2a;padding:10px 14px;border-radius:8px;margin-top:16px}</style></head><body><main>
<h1>CompactBench admin</h1><p class="muted">Signed in as ${esc(email)} · read-only</p>
${summary.errors.length ? `<div class="errors">${summary.errors.map(esc).join("<br>")}</div>` : ""}
<h2>Submissions</h2>
<p class="muted">${summary.counts.day} today · ${summary.counts.week} this week · ${summary.counts.active} in progress · ${summary.counts.failed_week} failed this week</p>
${table(["Run", "Method", "Model", "Status", "Score", "Submitted"], summary.submissions.map((s) => [link(new URL(`/status?id=${encodeURIComponent(s.id)}`, siteUrl).toString(), s.id.slice(0, 8)), td(`@${s.handle} / ${s.method_name} ${s.method_version}`), td(s.model_label ? `${s.model_label} (${s.provider})` : `${s.provider}/${s.model}`, "mono"), `<td class="${statusClass(s)}" title="${esc(s.message ?? "")}">${esc(s.stuck ? `${s.status} — stuck?` : s.status)}</td>`, td(s.score === null ? "—" : pct(s.score), "mono"), td(s.created_at.slice(0, 16).replace("T", " "), "mono")]))}
<p class="muted"><a href="/export/submissions.csv">Export all submissions (CSV)</a></p>
<h2>Flags</h2>
${summary.flags.length ? table(["Submission", "Why it's worth a look"], summary.flags.map((f) => [td(f.method), td(f.reason, "warn")])) : `<p class="muted">No flags.</p>`}
<h2>Ranked evaluations</h2>
${table(["Run", "For", "Result", "Started", "Minutes"], summary.runs.map((r) => [link(r.url, r.id), td(r.title), td(r.conclusion ?? r.status, r.conclusion === "success" ? "good" : r.conclusion ? "bad" : "warn"), td(r.started.slice(0, 16).replace("T", " "), "mono"), td(r.minutes, "mono")]))}
<h2>Family difficulty</h2>
${table(["Family", "Best", "Best method", "Median", "Rows"], summary.families.map((f) => [td(f.family), td(pct(f.best), "mono"), td(f.best_method), td(pct(f.median), "mono"), td(f.rows, "mono")]))}
<h2>Leaderboard (${summary.leaderboard.length} rows)</h2>
${table(["Method", "Kind", "Model", "Season", "Score", "95% CI", "Published"], summary.leaderboard.map((r) => [td(`${r.method_name} ${r.method_version}`), td(r.row_kind, "muted"), td(r.compactor_model, "mono"), td(r.season ?? "—"), td(pct(r.score), "mono"), td(`${pct(r.score_ci_low)}–${pct(r.score_ci_high)}`, "mono muted"), td(r.published_at.slice(0, 10), "mono")]))}
</main></body></html>`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const config: AccessConfig = { teamDomain: env.ACCESS_TEAM_DOMAIN, audience: env.ACCESS_AUD, ownerEmail: env.OWNER_EMAIL };
    const email = await verifyAccess(request.headers.get("Cf-Access-Jwt-Assertion"), config);
    if (!email) return new Response("Forbidden", { status: 403 });
    const headers = { "Cache-Control": "no-store", "X-Robots-Tag": "noindex" };
    if (new URL(request.url).pathname === "/export/submissions.csv") {
      if (!env.DB) return new Response("No submissions database bound", { status: 503, headers });
      return new Response(await exportSubmissions(env.DB), {
        headers: { ...headers, "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="submissions.csv"' },
      });
    }
    const summary = await summarize(env);
    if (new URL(request.url).pathname === "/api/summary") return Response.json(summary, { headers });
    return new Response(render(summary, email, env.SITE_URL), {
      headers: { ...headers, "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'" },
    });
  },
};
