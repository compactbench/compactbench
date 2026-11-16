// node --test worker/report.test.ts  (Node 24 strips the types)
import assert from "node:assert/strict";
import { test } from "node:test";
import { buildDailyReport, MemoryStatsStore, newMilestones, rawReport, reportText, type ReportEnv } from "./report.ts";

const env: ReportEnv = {
  CF_ANALYTICS_TOKEN: "t",
  CF_ZONE_TAG: "z",
  GITHUB_REPO: "compactbench/compactbench",
  HF_DATASET: "compactbench/compactbench",
  PYPI_PACKAGE: "compactbench",
};
const NOW = new Date("2026-12-02T14:00:00Z");

function fakeFetch(overrides: Record<string, unknown> = {}): typeof fetch {
  const responses: Record<string, unknown> = {
    "https://api.cloudflare.com/client/v4/graphql": {
      data: { viewer: { zones: [{ httpRequests1dGroups: [{
        sum: { requests: 9000, pageViews: 3100, threats: 12, countryMap: [
          { clientCountryName: "US", requests: 5000 }, { clientCountryName: "DE", requests: 2000 }, { clientCountryName: "IN", requests: 1000 },
        ] },
        uniq: { uniques: 1240 },
      }] }] } },
    },
    "https://api.github.com/repos/compactbench/compactbench": { stargazers_count: 104, forks_count: 9, open_issues_count: 3 },
    "https://huggingface.co/api/datasets/compactbench/compactbench": { downloads: 230, likes: 5 },
    "https://pypistats.org/api/packages/compactbench/recent": { data: { last_day: 40, last_week: 210, last_month: 900 } },
    ...overrides,
  };
  return (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (!(url in responses) || responses[url] === null) return new Response("nope", { status: 500 });
    return Response.json(responses[url]);
  }) as typeof fetch;
}

test("a day's report gathers traffic, activity and growth", async () => {
  const store = new MemoryStatsStore();
  await store.bump("2026-12-01", "selftest_score", 3);
  await store.bump("2026-12-01", "mcp_tool:selftest_score", 3);
  await store.bump("2026-12-01", "mcp_tool:get_leaderboard", 7);
  await store.bump("2026-12-01", "mcp_session", 4);
  await store.bump("2026-12-01", "contact", 1);
  await store.saveSnapshot("2026-11-30", { visitors_day: 1000, github_stars: 98 });
  store.subs = { newByStatus: { published: 2, failed: 1 }, total: 12, published: 9, people: 6, referenceRuns: 4 };

  const report = await buildDailyReport(env, store, NOW, fakeFetch());
  const text = reportText(report);
  assert.equal(report.day, "2026-12-01");
  assert.match(text, /Visitors\s+1,240 \(\+240, \+24% vs the day before\)/);
  assert.match(text, /Top countries\s+US 63%, DE 25%, IN 13%/);
  assert.match(text, /New runs\s+3 \(2 published, 1 failed\)/);
  assert.match(text, /AI self-tests\s+3 scored yesterday, 3 in all/);
  assert.match(text, /get_leaderboard 7, selftest_score 3/);
  assert.match(text, /104 stars \(\+6, \+6% vs the day before\), 9 forks/);
  assert.match(text, /PyPI\s+40 yesterday, 210 this week, 900 this month/);
  assert.match(text, /Contact\s+1 message\n/);
  assert.ok(report.milestones.includes("100 GitHub stars"));
  assert.ok(report.milestones.includes("1,000 visitors in one day"));
  assert.ok(report.milestones.includes("The first AI took the self-test!"));
  assert.deepEqual(await store.snapshot("2026-12-01").then((s) => s.github_stars), 104);
});

test("each milestone is announced once", async () => {
  const store = new MemoryStatsStore();
  const first = await buildDailyReport(env, store, NOW, fakeFetch());
  assert.ok(first.milestones.length > 0);
  const again = await buildDailyReport(env, store, new Date("2026-12-03T14:00:00Z"), fakeFetch());
  assert.deepEqual(again.milestones, []);
});

test("a missing or failing source doesn't stop the report", async () => {
  const report = await buildDailyReport(
    { GITHUB_REPO: "compactbench/compactbench" },
    new MemoryStatsStore(),
    NOW,
    fakeFetch({ "https://api.github.com/repos/compactbench/compactbench": null }),
  );
  const text = reportText(report);
  assert.match(text, /Traffic\s+not available/);
  assert.match(text, /Hugging Face\s+not available/);
  assert.match(text, /GitHub\s+n\/a stars/);
});

test("only the highest new threshold is announced, and lower ones are recorded", () => {
  const crossed = newMilestones({ github_stars: 60 }, new Set(["github_stars:10"]));
  assert.deepEqual(crossed.filter((m) => m.text).map((m) => m.text), ["50 GitHub stars"]);
  assert.deepEqual(crossed.map((m) => m.key).sort(), ["github_stars:25", "github_stars:50"]);
});

test("the email is plain text with a summary subject", async () => {
  const report = await buildDailyReport(env, new MemoryStatsStore(), NOW, fakeFetch());
  const raw = rawReport(report, { from: "reports@compactbench.test", to: "owner@example.org", id: "1", now: NOW, host: "x" });
  assert.match(raw, /\r\nSubject: CompactBench 2026-12-01: 1,240 visitors, 0 new runs, 104 stars - milestone!\r\n/);
  const body = Buffer.from(raw.split("\r\n\r\n")[1]!.replace(/\r\n/g, ""), "base64").toString("utf8");
  assert.match(body, /^CompactBench, 2026-12-01 \(UTC\)/);
});
