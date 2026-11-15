// AI self-test over MCP: an AI compacts a public CompactBench case with its own model,
// answers the multiple-choice questions from its own memory, and the Worker scores the
// letters. No model call happens here, so a self-test costs the site nothing.
//
// The scoring mirrors compactbench.scoring for choice questions: a single choice is right
// or wrong; select-all scores (right - wrong) / correct, floored at 0; a question whose
// right answer is "not stated" only counts when missed; the overall score averages the
// failure families so each counts equally.

export interface Question {
  id: string;
  family: string;
  format: "single" | "multi";
  question: string;
  options: string[];
}

export interface SelfTestCase {
  id: string;
  size: "quick" | "full";
  suite: string;
  family: string;
  difficulty: string;
  cycles: { cycle: number; turns: string; questions: Question[] }[];
}

export interface Key {
  cycle: number;
  family: string;
  format: "single" | "multi";
  answer: string[];
  stale: string[];
  traps: string[];
  abstain: boolean;
}

export interface SelfTestData {
  budget_tokens: number;
  cases: SelfTestCase[];
  keys: Record<string, Record<string, Key>>;
}

type Json = Record<string, unknown>;

const HOW = [
  "How the self-test works (it mirrors a CompactBench run):",
  "1. selftest_turns with cycle 0 gives the opening conversation. Compact it into your memory, as you would before your context runs out. Keep the memory under the token budget.",
  "2. selftest_questions for cycle 0 gives the questions asked after that compaction. Answer them from your memory only — ideally in a fresh context or a subagent that sees nothing but the memory.",
  "3. selftest_turns for the next cycle gives only the new turns. Update your memory from your previous memory plus those turns (the earlier turns are gone), then answer that cycle's questions. Repeat for every cycle.",
  "4. selftest_score with all your answers, e.g. {\"c0-q1\": \"B\", \"c0-q2\": [\"A\", \"D\"]}, returns your score overall, after each compaction and per failure family, with what you got wrong.",
  "The score is self-reported practice on public cases: useful to compare compaction prompts, not a leaderboard result.",
].join("\n");

export const SELFTEST_TOOLS = [
  {
    name: "selftest_list",
    description:
      "List the self-test cases an AI can take to measure how much its own context compaction forgets. Each case is a public CompactBench conversation compacted several times; quick cases are short, full cases are ranked-size.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "selftest_turns",
    description:
      "The conversation turns for one cycle of a self-test case: cycle 0 is the opening conversation, later cycles only the new turns. Compact them into your memory before asking for the questions.",
    inputSchema: {
      type: "object",
      properties: {
        case: { type: "string", description: "A case id from selftest_list, e.g. quick-decision-override or full-1" },
        cycle: { type: "integer", minimum: 0, default: 0 },
      },
      required: ["case"],
    },
  },
  {
    name: "selftest_questions",
    description:
      "The multiple-choice questions asked after compacting one cycle. Answer from your compacted memory only, with option letters.",
    inputSchema: {
      type: "object",
      properties: { case: { type: "string" }, cycle: { type: "integer", minimum: 0 } },
      required: ["case", "cycle"],
    },
  },
  {
    name: "selftest_score",
    description:
      "Score your answers to a self-test case: one letter per single-choice question, a list of letters (possibly empty) per select-all question. Unanswered questions count as wrong.",
    inputSchema: {
      type: "object",
      properties: {
        case: { type: "string" },
        answers: {
          type: "object",
          description: "Question id to letter(s), e.g. {\"c0-q1\": \"B\", \"c0-q2\": [\"A\", \"D\"]}",
          additionalProperties: { anyOf: [{ type: "string" }, { type: "array", items: { type: "string" } }] },
        },
      },
      required: ["case", "answers"],
    },
  },
];

export class SelfTestError extends Error {}

function findCase(data: SelfTestData, id: unknown): SelfTestCase {
  const want = String(id ?? "").trim().toLowerCase();
  const found = data.cases.find((c) => c.id === want);
  if (!found) throw new SelfTestError(`Unknown case ${JSON.stringify(id)}. Call selftest_list for the case ids.`);
  return found;
}

function findCycle(item: SelfTestCase, cycle: unknown) {
  const n = Number(cycle ?? 0);
  const found = item.cycles.find((c) => c.cycle === n);
  if (!found) throw new SelfTestError(`Case ${item.id} has cycles 0 to ${item.cycles.length - 1}.`);
  return found;
}

const approxTokens = (text: string) => Math.round(text.length / 4);

/** Letters picked in one answer, or null when it isn't a readable answer. */
export function parseLetters(raw: unknown, format: "single" | "multi", count: number): string[] | null {
  let parts: string[];
  if (Array.isArray(raw)) parts = raw.map((v) => String(v));
  else if (typeof raw === "string") {
    const text = raw.trim();
    if (format === "multi" && /^(none|\[\])?$/i.test(text)) return [];
    parts = text.split(/[\s,;]+/);
  } else return null;
  const valid = new Set(Array.from({ length: count }, (_, i) => String.fromCharCode(65 + i)));
  const letters: string[] = [];
  for (const part of parts) {
    if (!part.trim()) continue;
    const match = /^[\s("']*([A-Za-z])[\s.)"':]*$/.exec(part);
    if (!match) return null;
    const letter = match[1].toUpperCase();
    if (!valid.has(letter)) return null;
    if (!letters.includes(letter)) letters.push(letter);
  }
  return letters.sort();
}

interface Outcome {
  id: string;
  score: number;
  counted: boolean;
  picked: string[] | null;
  stale: boolean;
  trapped: boolean;
}

export function scoreOne(id: string, key: Key, options: number, raw: unknown): Outcome {
  const picked = raw === undefined ? null : parseLetters(raw, key.format, options);
  let score = 0;
  if (picked !== null) {
    if (key.format === "single") score = picked.length === 1 && picked[0] === key.answer[0] ? 1 : 0;
    else if (!key.answer.length) score = picked.length ? 0 : 1;
    else {
      const right = picked.filter((l) => key.answer.includes(l)).length;
      const wrong = picked.length - right;
      score = Math.max(0, (right - wrong) / key.answer.length);
    }
  }
  return {
    id,
    score,
    // A right "not stated" earns nothing (an empty memory gets it right too); a miss counts.
    counted: !(key.abstain && score >= 1),
    picked,
    stale: !!picked?.some((l) => key.stale.includes(l)),
    trapped: !!picked?.some((l) => key.traps.includes(l)),
  };
}

const mean = (values: number[]) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);
const pct = (v: number | null) => (v === null ? "-" : (v * 100).toFixed(1));

export function callSelfTest(data: SelfTestData, name: string, args: Json): string | null {
  switch (name) {
    case "selftest_list": {
      const lines = data.cases.map((c) => {
        const tokens = approxTokens(c.cycles.map((x) => x.turns).join(""));
        const questions = c.cycles.reduce((n, x) => n + x.questions.length, 0);
        const what = c.family === "mixed" ? "every failure family mixed" : c.family.replace(/_/g, " ");
        return `${c.id}\t${c.size}\t${c.cycles.length} compactions\t~${tokens.toLocaleString("en-US")} tokens\t${questions} questions\t${what}`;
      });
      return [
        `Memory budget: ${data.budget_tokens} tokens per compaction (count it roughly as characters / 4).`,
        "case\tsize\tcompactions\tconversation\tquestions\ttests",
        ...lines,
        "",
        HOW,
      ].join("\n");
    }
    case "selftest_turns": {
      const item = findCase(data, args.case);
      const cycle = findCycle(item, args.cycle);
      const last = item.cycles.length - 1;
      const head =
        cycle.cycle === 0
          ? `Case ${item.id}, cycle 0 of ${last}: the opening conversation. Compact it into a memory of at most ${data.budget_tokens} tokens, then call selftest_questions for cycle 0.`
          : `Case ${item.id}, cycle ${cycle.cycle} of ${last}: only the turns since your last compaction. Update your memory (at most ${data.budget_tokens} tokens) from your previous memory and these turns, then call selftest_questions for cycle ${cycle.cycle}.`;
      return `${head}\n\n<conversation>\n${cycle.turns}\n</conversation>`;
    }
    case "selftest_questions": {
      const item = findCase(data, args.case);
      const cycle = findCycle(item, args.cycle);
      const blocks = cycle.questions.map(
        (q) => `${q.id} [${q.format === "single" ? "pick one" : "select all that apply; [] for none"}] ${q.question}\n${q.options.map((o) => `  ${o}`).join("\n")}`,
      );
      const next = cycle.cycle < item.cycles.length - 1
        ? `Then call selftest_turns for cycle ${cycle.cycle + 1}.`
        : "This is the last cycle: call selftest_score with all your answers.";
      return [
        `Answer from your compacted memory only. ${next}`,
        "",
        ...blocks,
      ].join("\n\n");
    }
    case "selftest_score": {
      const item = findCase(data, args.case);
      const keys = data.keys[item.id] ?? {};
      const answers = (args.answers ?? {}) as Json;
      if (typeof answers !== "object" || Array.isArray(answers)) throw new SelfTestError("answers must be an object of question id to letter(s).");
      const options = new Map(item.cycles.flatMap((c) => c.questions.map((q) => [q.id, q.options.length] as const)));
      const outcomes = Object.entries(keys).map(([id, key]) => ({ key, ...scoreOne(id, key, options.get(id) ?? 0, answers[id]) }));
      const counted = outcomes.filter((o) => o.counted);
      const families = [...new Set(counted.map((o) => o.key.family))].sort();
      const byFamily = families.map((f) => [f, mean(counted.filter((o) => o.key.family === f).map((o) => o.score))] as const);
      const overall = mean(byFamily.map(([, v]) => v ?? 0));
      const byCycle = item.cycles.map((c) => mean(counted.filter((o) => o.key.cycle === c.cycle).map((o) => o.score)));
      const answered = outcomes.filter((o) => o.picked !== null).length;
      const misses = outcomes.filter((o) => o.counted && o.score < 1);
      const lines = [
        `Self-test ${item.id}: ${pct(overall)} (family-balanced, ${counted.length} scored questions, ${answered} of ${outcomes.length} answered).`,
        `After each compaction: ${byCycle.map(pct).join(" -> ")}`,
        `Picked a superseded answer: ${outcomes.filter((o) => o.stale).length}; picked a decoy: ${outcomes.filter((o) => o.trapped).length}.`,
        "",
        "By family:",
        ...byFamily.map(([f, v]) => `  ${f}: ${pct(v)}`),
      ];
      if (misses.length) {
        lines.push("", "Missed:");
        for (const o of misses) {
          const why = o.picked === null ? "no readable answer" : `you picked ${o.picked.join(", ") || "none"}`;
          const flag = o.stale ? " (an earlier value the conversation replaced)" : o.trapped ? " (a decoy)" : "";
          lines.push(`  ${o.id}: ${why}${flag}; right: ${o.key.answer.join(", ") || "none"}`);
        }
      }
      lines.push(
        "",
        "A self-reported practice score on a public case. It isn't comparable with leaderboard scores: only the multiple-choice questions are asked, and your own model answers them.",
      );
      return lines.join("\n");
    }
    default:
      return null;
  }
}
