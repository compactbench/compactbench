// Plain-Markdown versions of the site's pages, for AI agents and llms.txt.
import datasheet from "../generated/datasheet.md?raw";
import methodology from "../generated/methodology.md?raw";
import privacy from "../generated/privacy.md?raw";
import submissionTerms from "../generated/submission-terms.md?raw";
import submitting from "../generated/submitting.md?raw";
import { families, ordered, pct, rows, season, suites } from "./data";

export function familiesMarkdown(): string {
  const lines = ["# Failure families", ""];
  lines.push(
    "Each family generates one kind of compaction failure. Practice and ranked cases are mixed",
    "sessions: every family in one conversation, under one token budget.",
    "",
  );
  for (const f of families) {
    lines.push(`## ${f.title} (\`${f.key}\`)`, "", f.description, "");
  }
  lines.push("## Suites", "");
  for (const s of suites) lines.push(`- \`${s.key}\`: ${s.description}`);
  lines.push(
    "- `elite` (hidden): the ranked set — mixed sessions in private worlds, sampled fresh per run.",
  );
  return lines.join("\n") + "\n";
}

export function leaderboardMarkdown(): string {
  const lines = [
    `# Leaderboard — season ${season.key}`,
    "",
    `Suite ${season.suite} ${season.suite_version}, budget ${season.budget_tokens} tokens,`,
    `${season.drift_cycles + 1} compactions, reader ${season.reader.model} (effort ${season.reader.effort ?? "default"}).`,
    "Score = % of questions answered correctly from the method's artifact, family-balanced, with 95% interval.",
    "",
  ];
  const list = ordered(rows);
  if (!list.length) {
    lines.push("Season 1 is being calibrated; no rows are published yet.");
    return lines.join("\n") + "\n";
  }
  lines.push("| Rank | Method | Kind | Model | Score | 95% CI | Drift |", "|---|---|---|---|---|---|---|");
  for (const r of list) {
    lines.push(
      `| ${r.rank ?? "—"} | ${r.method_name} ${r.method_version} | ${r.row_kind} | ${r.compactor_model} | ${pct(r.score)} | ${pct(r.score_ci_low)}–${pct(r.score_ci_high)} | ${pct(r.drift_resistance, 0)} |`,
    );
  }
  return lines.join("\n") + "\n";
}

export const pages: Record<string, { title: string; body: () => string }> = {
  methodology: { title: "Methodology", body: () => methodology },
  submit: { title: "Submit a method", body: () => submitting },
  families: { title: "Failure families", body: familiesMarkdown },
  leaderboard: { title: "Leaderboard", body: leaderboardMarkdown },
  datasheet: { title: "Datasheet", body: () => datasheet },
  privacy: { title: "Privacy", body: () => privacy },
  "submission-terms": { title: "Submission terms", body: () => submissionTerms },
};
