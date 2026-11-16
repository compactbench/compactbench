// node --test worker/mcp.test.ts  (Node 24 strips the types)
import assert from "node:assert/strict";
import { test } from "node:test";
import { type Data, handleHttp, handleMessage } from "./mcp.ts";

const data: Data = {
  season: { key: "s1", budget_tokens: 1024, drift_cycles: 4 },
  families: [
    { key: "buried_constraint", title: "Buried constraints", description: "Rules stated once." },
    { key: "task_continuity", title: "Task continuity", description: "A moving ticket board." },
  ],
  rows: [
    {
      rank: null, row_kind: "baseline", method_name: "hierarchical-summary", method_version: "2.0.0",
      compactor_model: "claude-haiku-5-5", season: "s1", score: 0.44, score_ci_low: 0.4, score_ci_high: 0.48,
      normalized_score: 0.46, drift_resistance: 0.9, stale_rate: 0.1, trap_rate: 0, hallucination_rate: 0,
      by_family: { buried_constraint: 0.5, task_continuity: 0.2 }, by_cycle: [0.5, 0.45, 0.4], cases: 6,
    },
    {
      rank: null, row_kind: "baseline", method_name: "naive-summary", method_version: "2.0.0",
      compactor_model: "claude-haiku-5-5", season: "s1", score: 0.38, score_ci_low: 0.34, score_ci_high: 0.42,
      normalized_score: 0.4, drift_resistance: 0.6, stale_rate: 0.2, trap_rate: 0, hallucination_rate: 0,
      by_family: { buried_constraint: 0.6, task_continuity: 0.1 }, by_cycle: [0.6, 0.4, 0.3], cases: 6,
    },
  ],
};

const call = (method: string, params: Record<string, unknown> = {}) =>
  handleMessage(data, { jsonrpc: "2.0", id: 1, method, params }) as Record<string, any>;

test("initialize negotiates a supported protocol version", () => {
  const reply = call("initialize", { protocolVersion: "2025-03-26" });
  assert.equal(reply.result.protocolVersion, "2025-03-26");
  assert.equal(call("initialize", { protocolVersion: "1999-01-01" }).result.protocolVersion, "2025-06-18");
  assert.ok(reply.result.capabilities.tools);
});

test("notifications get no reply", () => {
  assert.equal(handleMessage(data, { jsonrpc: "2.0", method: "notifications/initialized" }), null);
});

test("tools are listed and callable", () => {
  const names = call("tools/list").result.tools.map((t: { name: string }) => t.name);
  assert.deepEqual(names.sort(), ["compare_methods", "explain_metric", "get_leaderboard", "get_method", "list_families"]);
  const board = call("tools/call", { name: "get_leaderboard", arguments: { limit: 1 } }).result.content[0].text;
  assert.match(board, /hierarchical-summary/);
  assert.doesNotMatch(board, /naive-summary/);
  const cmp = call("tools/call", { name: "compare_methods", arguments: { a: "hierarchical", b: "naive" } }).result.content[0].text;
  assert.match(cmp, /task_continuity\t20\.0\t10\.0/);
  assert.match(call("tools/call", { name: "explain_metric", arguments: { metric: "ranking" } }).result.content[0].text, /interval/);
});

test("get_method takes handle/method to tell submitters apart", () => {
  const twin = (handle: string, score: number) => ({ ...data.rows[1]!, row_kind: "submission", method_name: "ledger", handle, score });
  const both: Data = { ...data, rows: [twin("alice", 0.5), twin("bob", 0.3)] };
  const get = (name: string) =>
    (handleMessage(both, { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "get_method", arguments: { name } } }) as Record<string, any>)
      .result.content[0].text as string;
  assert.match(get("ledger"), /"handle": "alice"/);
  assert.match(get("bob/ledger"), /"handle": "bob"/);
  assert.match(get("@Bob/ledger"), /"handle": "bob"/);
  const board = (handleMessage(both, { jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "get_leaderboard", arguments: {} } }) as Record<string, any>)
    .result.content[0].text as string;
  assert.match(board, /\tsubmitted by\t/);
  assert.match(board, /ledger [0-9.]+\t@alice\t/);
});

test("unknown methods and tools are JSON-RPC errors", () => {
  assert.equal(call("nope").error.code, -32601);
  assert.equal(call("tools/call", { name: "nope" }).error.code, -32602);
});

test("HTTP: POST answers, notifications get 202, GET is refused", async () => {
  const load = async () => data;
  const post = (body: unknown) =>
    handleHttp(new Request("https://x/mcp", { method: "POST", body: JSON.stringify(body) }), load);
  const ok = await post({ jsonrpc: "2.0", id: 7, method: "ping" });
  assert.equal(ok.status, 200);
  assert.deepEqual(await ok.json(), { jsonrpc: "2.0", id: 7, result: {} });
  assert.equal((await post({ jsonrpc: "2.0", method: "notifications/initialized" })).status, 202);
  assert.equal((await handleHttp(new Request("https://x/mcp"), load)).status, 405);
  const bad = await handleHttp(new Request("https://x/mcp", { method: "POST", body: "{" }), load);
  assert.equal(bad.status, 400);
});
