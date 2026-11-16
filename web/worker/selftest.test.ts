// node --test worker/selftest.test.ts  (Node 24 strips the types)
import assert from "node:assert/strict";
import { test } from "node:test";
import { handleMessage } from "./mcp.ts";
import { parseLetters, scoreOne, type Key, type SelfTestData } from "./selftest.ts";

const selftest: SelfTestData = {
  budget_tokens: 1024,
  cases: [
    {
      id: "quick-decision-override",
      size: "quick",
      suite: "starter@2.0.1",
      family: "decision_override",
      difficulty: "easy",
      cycles: [
        {
          cycle: 0,
          turns: "USER: We'll ship on Postgres.\n\nASSISTANT: Noted.",
          questions: [
            { id: "c0-q1", family: "decision_override", format: "single", question: "Which database?", options: ["A. MySQL", "B. Postgres", "C. Not stated in the conversation"] },
            { id: "c0-q2", family: "decision_override", format: "multi", question: "Which apply?", options: ["A. x", "B. y", "C. z"] },
          ],
        },
        {
          cycle: 1,
          turns: "USER: Switch to MySQL after all.",
          questions: [
            { id: "c1-q1", family: "decision_override", format: "single", question: "Which database now?", options: ["A. MySQL", "B. Postgres", "C. Not stated in the conversation"] },
            { id: "c1-q2", family: "buried_constraint", format: "single", question: "Who signs off?", options: ["A. Ana", "B. Ben", "C. Not stated in the conversation"] },
          ],
        },
      ],
    },
  ],
  keys: {
    "quick-decision-override": {
      "c0-q1": { cycle: 0, family: "decision_override", format: "single", answer: ["B"], stale: [], traps: [], abstain: false },
      "c0-q2": { cycle: 0, family: "decision_override", format: "multi", answer: ["A", "C"], stale: [], traps: ["B"], abstain: false },
      "c1-q1": { cycle: 1, family: "decision_override", format: "single", answer: ["A"], stale: ["B"], traps: [], abstain: false },
      "c1-q2": { cycle: 1, family: "buried_constraint", format: "single", answer: ["C"], stale: [], traps: [], abstain: true },
    },
  },
};

const data = {
  selftest,
  season: { key: "s1", budget_tokens: 1024, drift_cycles: 4 },
  families: [],
  rows: [],
};

const tool = (name: string, args: Record<string, unknown>) => {
  const reply = handleMessage(data, { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }) as Record<string, any>;
  return { text: reply.result.content[0].text as string, isError: reply.result.isError as boolean };
};

test("the self-test tools are listed with the others", () => {
  const reply = handleMessage(data, { jsonrpc: "2.0", id: 1, method: "tools/list" }) as Record<string, any>;
  const names = reply.result.tools.map((t: { name: string }) => t.name);
  for (const name of ["selftest_list", "selftest_turns", "selftest_questions", "selftest_score", "get_leaderboard"]) {
    assert.ok(names.includes(name), name);
  }
});

test("a case is handed out cycle by cycle, questions separately, without the answers", () => {
  assert.match(tool("selftest_list", {}).text, /quick-decision-override\tquick\t2 compactions/);
  const turns = tool("selftest_turns", { case: "quick-decision-override", cycle: 0 }).text;
  assert.match(turns, /at most 1024 tokens/);
  assert.match(turns, /<conversation>\nUSER: We'll ship on Postgres/);
  const later = tool("selftest_turns", { case: "quick-decision-override", cycle: 1 }).text;
  assert.doesNotMatch(later, /Postgres/, "a later cycle only has the new turns");
  const questions = tool("selftest_questions", { case: "quick-decision-override", cycle: 0 }).text;
  assert.match(questions, /c0-q1 \[pick one\] Which database\?\n {2}A\. MySQL/);
  assert.doesNotMatch(questions, /"answer"/);
  assert.match(questions, /selftest_turns for cycle 1/);
});

test("scoring follows the benchmark's rules for choice questions", () => {
  const { text, isError } = tool("selftest_score", {
    case: "quick-decision-override",
    answers: { "c0-q1": "b", "c0-q2": ["A", "B", "C"], "c1-q1": "B", "c1-q2": "C" },
  });
  assert.equal(isError, false);
  // decision_override: 1, (2 right - 1 wrong) / 2 = 0.5, 0 (stale) -> 0.5; the right "not
  // stated" doesn't count, so buried_constraint has no scored question.
  assert.match(text, /^Self-test quick-decision-override: 50\.0 \(family-balanced, 3 scored questions, 4 of 4 answered\)/);
  assert.match(text, /After each compaction: 75\.0 -> 0\.0/);
  assert.match(text, /Picked a superseded answer: 1; picked a decoy: 1\./);
  assert.match(text, /c1-q1: you picked B \(an earlier value the conversation replaced\); right: A/);
});

test("a missed 'not stated' counts, and unanswered questions are wrong", () => {
  const { text } = tool("selftest_score", { case: "quick-decision-override", answers: { "c1-q2": "A" } });
  assert.match(text, /4 scored questions, 1 of 4 answered/);
  assert.match(text, /c0-q1: no readable answer; right: B/);
});

test("bad input comes back as a tool error the model can fix", () => {
  const unknown = tool("selftest_turns", { case: "nope" });
  assert.equal(unknown.isError, true);
  assert.match(unknown.text, /selftest_list/);
  assert.equal(tool("selftest_questions", { case: "quick-decision-override", cycle: 9 }).isError, true);
  assert.equal(tool("selftest_score", { case: "quick-decision-override", answers: [] }).isError, true);
});

test("letters are read leniently but never guessed", () => {
  assert.deepEqual(parseLetters("(B)", "single", 3), ["B"]);
  assert.deepEqual(parseLetters("a, c", "multi", 3), ["A", "C"]);
  assert.deepEqual(parseLetters("none", "multi", 3), []);
  assert.deepEqual(parseLetters([], "multi", 3), []);
  assert.equal(parseLetters("Postgres", "single", 3), null);
  assert.equal(parseLetters("D", "single", 3), null, "past the last option");
  const key: Key = { cycle: 0, family: "f", format: "single", answer: ["A"], stale: [], traps: [], abstain: false };
  assert.equal(scoreOne("q", key, 3, "A, B").score, 0, "two picks on a single choice score 0");
});
