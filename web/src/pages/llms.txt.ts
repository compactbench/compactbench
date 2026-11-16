import type { APIRoute } from "astro";
import { families, season } from "../lib/data";
import { docs } from "../lib/docs";
import { pages } from "../lib/markdown";

// https://llmstxt.org — a map of the site for language models.
export const GET: APIRoute = ({ site }) => {
  const url = (path: string) => new URL(path, site).toString();
  const body = [
    "# CompactBench",
    "",
    "> The open benchmark for context compaction: long AI agent sessions compacted again and",
    "> again under a fixed token budget, scored mechanically on what survived.",
    "",
    `Current season: ${season.key} (suite ${season.suite} ${season.suite_version}, ${season.budget_tokens}-token budget,`,
    `${season.drift_cycles + 1} compactions). ${families.length} failure families. Python package: \`pip install compactbench\`.`,
    "",
    "## Pages",
    "",
    ...Object.entries(pages).map(([key, p]) => `- [${p.title}](${url(`/${key}.md`)})`),
    "",
    "## Docs",
    "",
    ...docs.map((d) => `- [${d.title}](${url(`/docs/${d.slug}.md`)}): ${d.description}`),
    "",
    "## Data",
    "",
    `- [Leaderboard JSON](${url("/api/leaderboard.json")}): every published row`,
    `- [Families JSON](${url("/api/families.json")}): failure families`,
    `- [Season JSON](${url("/api/season.json")}): the current season's pinned settings`,
    `- [Leaderboard CSV](${url("/api/leaderboard.csv")}): one row per result, one column per family`,
    `- [OpenAPI](${url("/api/openapi.json")}): description of the JSON API, incl. /api/methods/<slug>.json`,
    "",
    "## MCP",
    "",
    `- Remote MCP server: ${url("/mcp")} (Streamable HTTP, read-only). Tools: get_leaderboard, get_method, compare_methods, list_families, explain_metric.`,
    "- Self-test on the same server: selftest_list, selftest_turns, selftest_questions, selftest_score. Compact a public case with your own model, answer from your memory, and get a mechanical score overall, per compaction and per failure family (self-reported practice, not a leaderboard result).",
    "",
    `- [Contact](${url("/contact")}): report a problem, suggest an idea, partnerships and press`,
    `- [Support CompactBench](${url("/donate")}): donations (Ko-fi) and what they fund`,
    "",
    "## Elsewhere",
    "",
    "- [Public suites on Hugging Face](https://huggingface.co/datasets/compactbench/compactbench): practice, starter and drills as JSONL configs",
    "- Claude Code plugin: /plugin install compactbench --marketplace compactbench/compactbench (skills forget-less and measure-compaction)",
    "",
    "## Optional",
    "",
    `- [Everything in one file](${url("/llms-full.txt")})`,
    "- [Source code](https://github.com/compactbench/compactbench)",
    "",
  ].join("\n");
  return new Response(body, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
};
