// The owner's daily report: one email a day with traffic, activity and growth, plus a line
// for every milestone crossed. Everything counted is an aggregate (no visitor, IP or
// account is recorded), and every outside source is optional: a source that fails or
// isn't configured shows as "not available" instead of stopping the report.

import { base64Lines } from "./contact.ts";

export interface StatsStore {
  /** Add to a counter for one UTC day. */
  bump(day: string, event: string, by?: number): Promise<void>;
  events(day: string): Promise<Record<string, number>>;
  eventTotal(prefix: string): Promise<number>;
  saveSnapshot(day: string, values: Record<string, number>): Promise<void>;
  snapshot(day: string): Promise<Record<string, number>>;
  milestones(): Promise<Set<string>>;
  recordMilestone(key: string, day: string): Promise<void>;
  /** Runs created in [from, to), plus all-time totals. */
  submissions(from: string, to: string): Promise<SubmissionStats>;
}

export interface SubmissionStats {
  newByStatus: Record<string, number>;
  total: number;
  published: number;
  people: number;
  referenceRuns: number;
}

export interface ReportEnv {
  CF_ANALYTICS_TOKEN?: string;
  CF_ZONE_TAG?: string;
  GITHUB_STATS_TOKEN?: string;
  GITHUB_REPO: string;
  HF_DATASET?: string;
  PYPI_PACKAGE?: string;
}

export const MILESTONES: Record<string, { label: string; first?: string; at: number[] }> = {
  github_stars: { label: "GitHub stars", at: [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000] },
  visitors_day: { label: "visitors in one day", at: [100, 500, 1000, 5000, 10000, 50000] },
  submissions_total: { label: "ranked runs submitted", first: "The first ranked run was submitted", at: [1, 10, 25, 50, 100, 250, 500, 1000] },
  published_total: { label: "runs published on the leaderboard", first: "The first submitted run is on the leaderboard", at: [1, 10, 25, 50, 100, 250] },
  submitters_total: { label: "people have submitted runs", first: "The first person submitted a run", at: [1, 10, 25, 50, 100, 250] },
  selftests_total: { label: "AI self-tests scored", first: "The first AI took the self-test", at: [1, 10, 100, 1000, 10000] },
  hf_downloads: { label: "Hugging Face dataset downloads (30 days)", at: [10, 100, 1000, 10000] },
  pypi_month: { label: "PyPI downloads (30 days)", at: [100, 1000, 10000, 100000] },
};

export const dayOf = (date: Date) => date.toISOString().slice(0, 10);

type Fetcher = typeof fetch;
const UA = { "User-Agent": "compactbench-daily-report" };

async function getJson(fetcher: Fetcher, url: string, init: RequestInit = {}): Promise<Record<string, any> | null> {
  try {
    const response = await fetcher(url, { ...init, headers: { ...UA, ...(init.headers ?? {}) } });
    return response.ok ? ((await response.json()) as Record<string, any>) : null;
  } catch {
    return null;
  }
}

export interface Traffic {
  visitors: number;
  pageViews: number;
  requests: number;
  threats: number;
  countries: [string, number][];
}

/** Yesterday's zone analytics from Cloudflare's GraphQL API (free plan dataset). */
export async function cloudflareTraffic(env: ReportEnv, day: string, fetcher: Fetcher): Promise<Traffic | null> {
  if (!env.CF_ANALYTICS_TOKEN || !env.CF_ZONE_TAG) return null;
  const query = `query ($zone: string, $date: Date) { viewer { zones(filter: {zoneTag: $zone}) {
    httpRequests1dGroups(limit: 1, filter: {date: $date}) {
      sum { requests pageViews threats countryMap { clientCountryName requests } }
      uniq { uniques } } } } }`;
  const body = await getJson(fetcher, "https://api.cloudflare.com/client/v4/graphql", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.CF_ANALYTICS_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables: { zone: env.CF_ZONE_TAG, date: day } }),
  });
  const group = body?.data?.viewer?.zones?.[0]?.httpRequests1dGroups?.[0];
  if (!group) return null;
  const countries = ((group.sum?.countryMap ?? []) as { clientCountryName: string; requests: number }[])
    .sort((a, b) => b.requests - a.requests)
    .slice(0, 5)
    .map((c) => [c.clientCountryName, c.requests] as [string, number]);
  return {
    visitors: group.uniq?.uniques ?? 0,
    pageViews: group.sum?.pageViews ?? 0,
    requests: group.sum?.requests ?? 0,
    threats: group.sum?.threats ?? 0,
    countries,
  };
}

/** Public counts from GitHub, Hugging Face and PyPI. Missing ones are left out. */
export async function outsideNumbers(env: ReportEnv, fetcher: Fetcher): Promise<Record<string, number>> {
  const out: Record<string, number> = {};
  const repo = await getJson(fetcher, `https://api.github.com/repos/${env.GITHUB_REPO}`);
  if (repo) {
    out.github_stars = repo.stargazers_count ?? 0;
    out.github_forks = repo.forks_count ?? 0;
    out.github_open_issues = repo.open_issues_count ?? 0;
  }
  if (env.GITHUB_STATS_TOKEN) {
    const auth = { headers: { Authorization: `Bearer ${env.GITHUB_STATS_TOKEN}` } };
    const views = await getJson(fetcher, `https://api.github.com/repos/${env.GITHUB_REPO}/traffic/views`, auth);
    const clones = await getJson(fetcher, `https://api.github.com/repos/${env.GITHUB_REPO}/traffic/clones`, auth);
    if (views) {
      out.github_views_14d = views.count ?? 0;
      out.github_viewers_14d = views.uniques ?? 0;
    }
    if (clones) out.github_clones_14d = clones.count ?? 0;
  }
  if (env.HF_DATASET) {
    const hf = await getJson(fetcher, `https://huggingface.co/api/datasets/${env.HF_DATASET}`);
    if (hf) {
      out.hf_downloads = hf.downloads ?? 0;
      out.hf_likes = hf.likes ?? 0;
    }
  }
  if (env.PYPI_PACKAGE) {
    const pypi = await getJson(fetcher, `https://pypistats.org/api/packages/${env.PYPI_PACKAGE}/recent`);
    if (pypi?.data) {
      out.pypi_day = pypi.data.last_day ?? 0;
      out.pypi_week = pypi.data.last_week ?? 0;
      out.pypi_month = pypi.data.last_month ?? 0;
    }
  }
  return out;
}

const fmt = (n: number | undefined | null) => (n === undefined || n === null ? "n/a" : Math.round(n).toLocaleString("en-US"));

function change(now: number | undefined, before: number | undefined): string {
  if (now === undefined || before === undefined) return "";
  const delta = now - before;
  if (delta === 0) return " (no change)";
  const pct = before ? ` ${delta > 0 ? "+" : ""}${Math.round((delta / before) * 100)}%` : "";
  return ` (${delta > 0 ? "+" : ""}${fmt(delta)}${pct ? `,${pct}` : ""} vs the day before)`;
}

/** Thresholds crossed by today's values that haven't been announced before. */
export function newMilestones(values: Record<string, number>, reached: Set<string>): { key: string; text: string }[] {
  const out: { key: string; text: string }[] = [];
  for (const [metric, { label, first, at }] of Object.entries(MILESTONES)) {
    const value = values[metric];
    if (value === undefined) continue;
    const crossed = at.filter((t) => value >= t && !reached.has(`${metric}:${t}`));
    // Announce only the highest new threshold, but record every one so none repeats.
    if (crossed.length) {
      const top = crossed[crossed.length - 1]!;
      out.push({ key: `${metric}:${top}`, text: top === 1 && first ? `${first}!` : `${fmt(top)} ${label}` });
      for (const t of crossed.slice(0, -1)) out.push({ key: `${metric}:${t}`, text: "" });
    }
  }
  return out;
}

export interface ReportInput {
  day: string;
  traffic: Traffic | null;
  events: Record<string, number>;
  submissions: SubmissionStats;
  outside: Record<string, number>;
  previous: Record<string, number>;
  totals: { selftests: number };
  milestones: string[];
}

/** The email body. Plain text that reads well in any mail app. */
export function reportText(r: ReportInput): string {
  const lines: string[] = [];
  const add = (label: string, text: string) => lines.push(`${label.padEnd(16)}${text}`);
  const ev = (key: string) => r.events[key] ?? 0;
  const mcpTools = Object.entries(r.events)
    .filter(([k]) => k.startsWith("mcp_tool:"))
    .sort((a, b) => b[1] - a[1])
    .map(([k, n]) => `${k.slice(9)} ${fmt(n)}`);

  lines.push(`CompactBench, ${r.day} (UTC)`, "");
  if (r.milestones.length) {
    lines.push("Milestones");
    for (const m of r.milestones) lines.push(`  * ${m}`);
    lines.push("");
  }
  lines.push("Website");
  if (r.traffic) {
    add("  Visitors", `${fmt(r.traffic.visitors)}${change(r.traffic.visitors, r.previous.visitors_day)}`);
    add("  Page views", fmt(r.traffic.pageViews));
    add("  Requests", `${fmt(r.traffic.requests)} (${fmt(r.traffic.threats)} blocked as threats)`);
    if (r.traffic.countries.length) {
      const total = r.traffic.countries.reduce((a, [, n]) => a + n, 0) || 1;
      add("  Top countries", r.traffic.countries.map(([c, n]) => `${c} ${Math.round((n / total) * 100)}%`).join(", "));
    }
  } else {
    add("  Traffic", "not available (set CF_ANALYTICS_TOKEN and CF_ZONE_TAG)");
  }
  add("  Sign-ins", fmt(ev("signin")));
  add("  My runs views", fmt(ev("my_runs")));
  add("  Contact", `${fmt(ev("contact"))} message${ev("contact") === 1 ? "" : "s"}`);
  lines.push("");

  lines.push("Benchmark");
  const s = r.submissions;
  const newRuns = Object.values(s.newByStatus).reduce((a, b) => a + b, 0);
  const byStatus = Object.entries(s.newByStatus).map(([k, n]) => `${n} ${k}`).join(", ");
  add("  New runs", `${fmt(newRuns)}${byStatus ? ` (${byStatus})` : ""}`);
  add("  All runs", `${fmt(s.total)} submitted, ${fmt(s.published)} published, ${fmt(s.people)} people, ${fmt(s.referenceRuns)} on reference methods`);
  add("  AI self-tests", `${fmt(ev("selftest_score"))} scored yesterday, ${fmt(r.totals.selftests)} in all`);
  add("  MCP", `${fmt(ev("mcp_session"))} sessions, ${fmt(mcpTools.length ? Object.entries(r.events).filter(([k]) => k.startsWith("mcp_tool:")).reduce((a, [, n]) => a + n, 0) : 0)} tool calls`);
  if (mcpTools.length) add("", mcpTools.join(", "));
  lines.push("");

  lines.push("Elsewhere");
  const o = r.outside;
  const plural = (n: number | undefined, word: string) => `${fmt(n)} ${word}${n === 1 ? "" : "s"}`;
  add("  GitHub", `${plural(o.github_stars, "star")}${change(o.github_stars, r.previous.github_stars)}, ${plural(o.github_forks, "fork")}, ${fmt(o.github_open_issues)} open issues and PRs`);
  if (o.github_views_14d !== undefined) {
    add("", `${fmt(o.github_views_14d)} views by ${fmt(o.github_viewers_14d)} people and ${fmt(o.github_clones_14d)} clones in 14 days`);
  }
  add("  Hugging Face", o.hf_downloads === undefined ? "not available" : `${fmt(o.hf_downloads)} downloads (30 days), ${fmt(o.hf_likes)} likes`);
  add("  PyPI", o.pypi_month === undefined ? "not available" : `${fmt(o.pypi_day)} yesterday, ${fmt(o.pypi_week)} this week, ${fmt(o.pypi_month)} this month`);
  lines.push("", "Counts are totals only: no visitor, address or account is recorded for this report.");
  return lines.join("\n");
}

export function subjectFor(r: ReportInput): string {
  const parts = [
    r.traffic ? `${fmt(r.traffic.visitors)} visitors` : null,
    `${fmt(Object.values(r.submissions.newByStatus).reduce((a, b) => a + b, 0))} new runs`,
    r.outside.github_stars !== undefined ? `${fmt(r.outside.github_stars)} stars` : null,
  ].filter(Boolean);
  return `CompactBench ${r.day}: ${parts.join(", ")}${r.milestones.length ? " - milestone!" : ""}`;
}

export function rawReport(r: ReportInput, o: { from: string; to: string; id: string; now: Date; host: string }): string {
  const headers = [
    `From: CompactBench reports <${o.from}>`,
    `To: <${o.to}>`,
    `Subject: ${subjectFor(r)}`,
    `Date: ${o.now.toUTCString()}`,
    `Message-ID: <${o.id}@${o.host}>`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
  ];
  return `${headers.join("\r\n")}\r\n\r\n${base64Lines(reportText(r))}\r\n`;
}

/** Gather yesterday's numbers, record today's snapshot and milestones, and build the email. */
export async function buildDailyReport(
  env: ReportEnv,
  store: StatsStore,
  now: Date,
  fetcher: Fetcher,
): Promise<ReportInput> {
  const day = dayOf(new Date(now.getTime() - 86_400_000));
  const before = dayOf(new Date(now.getTime() - 2 * 86_400_000));
  const [traffic, outside, events, submissions, previous, reached, selftests] = await Promise.all([
    cloudflareTraffic(env, day, fetcher),
    outsideNumbers(env, fetcher),
    store.events(day),
    store.submissions(`${day}T00:00:00.000Z`, `${dayOf(now)}T00:00:00.000Z`),
    store.snapshot(before),
    store.milestones(),
    store.eventTotal("selftest_score"),
  ]);
  const values: Record<string, number> = {
    ...outside,
    submissions_total: submissions.total,
    published_total: submissions.published,
    submitters_total: submissions.people,
    selftests_total: selftests,
    ...(traffic ? { visitors_day: traffic.visitors, pageviews_day: traffic.pageViews } : {}),
  };
  const crossed = newMilestones(values, reached);
  await store.saveSnapshot(day, values);
  for (const m of crossed) await store.recordMilestone(m.key, day);
  return {
    day,
    traffic,
    events,
    submissions,
    outside,
    previous,
    totals: { selftests },
    milestones: crossed.map((m) => m.text).filter(Boolean),
  };
}

/** In-memory store for tests. */
export class MemoryStatsStore implements StatsStore {
  counts = new Map<string, number>();
  snapshots = new Map<string, Record<string, number>>();
  reached = new Set<string>();
  subs: SubmissionStats = { newByStatus: {}, total: 0, published: 0, people: 0, referenceRuns: 0 };

  async bump(day: string, event: string, by = 1): Promise<void> {
    this.counts.set(`${day}|${event}`, (this.counts.get(`${day}|${event}`) ?? 0) + by);
  }
  async events(day: string): Promise<Record<string, number>> {
    const out: Record<string, number> = {};
    for (const [k, n] of this.counts) if (k.startsWith(`${day}|`)) out[k.slice(day.length + 1)] = n;
    return out;
  }
  async eventTotal(prefix: string): Promise<number> {
    let total = 0;
    for (const [k, n] of this.counts) if (k.split("|")[1]!.startsWith(prefix)) total += n;
    return total;
  }
  async saveSnapshot(day: string, values: Record<string, number>): Promise<void> {
    this.snapshots.set(day, { ...values });
  }
  async snapshot(day: string): Promise<Record<string, number>> {
    return this.snapshots.get(day) ?? {};
  }
  async milestones(): Promise<Set<string>> {
    return new Set(this.reached);
  }
  async recordMilestone(key: string): Promise<void> {
    this.reached.add(key);
  }
  async submissions(): Promise<SubmissionStats> {
    return this.subs;
  }
}
