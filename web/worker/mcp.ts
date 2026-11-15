// A stateless MCP server (Streamable HTTP, JSON responses) over the site's public data.
// No SDK: the protocol surface used here is small — initialize, tools/list, tools/call.

export interface Data {
  rows: Row[];
  families: { key: string; title: string; description: string }[];
  season: Record<string, unknown> & { key: string; budget_tokens: number; drift_cycles: number };
}

interface Row {
  rank: number | null;
  row_kind: string;
  method_name: string;
  method_version: string;
  handle?: string | null;
  compactor_model: string;
  model_label?: string | null;
  season: string | null;
  score: number;
  score_ci_low: number;
  score_ci_high: number;
  normalized_score: number | null;
  drift_resistance: number;
  stale_rate: number;
  trap_rate: number;
  hallucination_rate: number;
  by_family: Record<string, number>;
  by_cycle: number[];
  cases: number;
}

type Json = Record<string, unknown>;

export const SUPPORTED_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"];

const METRICS: Record<string, string> = {
  score:
    "Share of probes the fixed reader answers correctly from the method's artifact after each compaction, averaged per family so every family counts equally. Reported with a 95% bootstrap interval. Abstention probes only count when missed.",
  normalized_score:
    "Per family, (score - null) / (oracle - null): how much of the achievable range the method kept, where oracle answers from the full conversation and null from nothing.",
  drift_resistance:
    "On probes asked after both the first and the last compaction, the last score over the first, averaged over cases. 1.0 means nothing was lost to repeated compaction.",
  decay: "The same probes' score after the first compaction minus after the last.",
  stale_rate: "Of probes that offered a superseded answer, the share where the reader picked it.",
  trap_rate:
    "Of probes that offered a decoy-only answer (another project's rule, a rejected proposal, an injected claim), the share where the reader picked it.",
  hallucination_rate:
    "Of 'never settled' probes, the share where the reader gave a concrete answer instead of 'not stated'.",
  budget:
    "Every artifact has a token budget (cl100k_base on the rendered artifact). Anything beyond it is cut before the reader sees it; ranked runs reject over-budget cycles.",
  ranking:
    "Rows are ordered by score. A rank is one plus the number of rows whose whole 95% interval lies above, so rows whose intervals overlap share a rank.",
};

const TOOLS = [
  {
    name: "get_leaderboard",
    description: "Current CompactBench leaderboard rows: method, model, score with 95% CI, drift resistance.",
    inputSchema: {
      type: "object",
      properties: {
        kind: { type: "string", enum: ["all", "submission", "baseline", "control"], default: "all" },
        limit: { type: "integer", minimum: 1, maximum: 100, default: 20 },
      },
    },
  },
  {
    name: "get_method",
    description: "Full results for one method: score, per-family scores, score after each compaction.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Method name, e.g. hierarchical-summary, or handle/method for one submitter's" },
      },
      required: ["name"],
    },
  },
  {
    name: "compare_methods",
    description: "Compare two methods overall, per failure family and per compaction.",
    inputSchema: {
      type: "object",
      properties: { a: { type: "string" }, b: { type: "string" } },
      required: ["a", "b"],
    },
  },
  {
    name: "list_families",
    description: "The failure families CompactBench tests, with what each one breaks.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "explain_metric",
    description: "Definition of a CompactBench metric or rule.",
    inputSchema: {
      type: "object",
      properties: { metric: { type: "string", enum: Object.keys(METRICS) } },
      required: ["metric"],
    },
  },
];

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "-" : (v * 100).toFixed(1));

/** A row by method name, or "handle/method" to pick one submitter's; best score first. */
function find(data: Data, name: unknown): Row | undefined {
  let want = String(name ?? "").toLowerCase().trim().replace(/^@/, "");
  let rows = data.rows;
  const slash = want.indexOf("/");
  if (slash > 0) {
    const handle = want.slice(0, slash);
    rows = rows.filter((r) => (r.handle ?? "").toLowerCase() === handle);
    want = want.slice(slash + 1);
  }
  return rows.find((r) => r.method_name.toLowerCase() === want) ?? rows.find((r) => r.method_name.toLowerCase().includes(want));
}

function callTool(data: Data, name: string, args: Json): string {
  switch (name) {
    case "get_leaderboard": {
      const kind = String(args.kind ?? "all");
      const limit = Math.min(Math.max(Number(args.limit ?? 20) || 20, 1), 100);
      const rows = data.rows.filter((r) => kind === "all" || r.row_kind === kind).slice(0, limit);
      if (!rows.length) return `No rows published yet for season ${data.season.key}.`;
      const lines = rows.map(
        (r) =>
          `${r.rank ?? "-"}\t${r.method_name} ${r.method_version}\t${r.row_kind}\t${r.model_label || r.compactor_model}\t${pct(r.score)} (${pct(r.score_ci_low)}-${pct(r.score_ci_high)})\tdrift ${pct(r.drift_resistance)}`,
      );
      return [`Season ${data.season.key}, budget ${data.season.budget_tokens} tokens.`, "rank\tmethod\tkind\tmodel\tscore (95% CI)\tdrift", ...lines].join("\n");
    }
    case "get_method": {
      const row = find(data, args.name);
      if (!row) return `No method named ${JSON.stringify(args.name)} on the leaderboard.`;
      return JSON.stringify(row, null, 2);
    }
    case "compare_methods": {
      const a = find(data, args.a);
      const b = find(data, args.b);
      if (!a || !b) return "Both methods must be on the leaderboard.";
      const lines = [`metric\t${a.method_name}\t${b.method_name}`, `score\t${pct(a.score)}\t${pct(b.score)}`];
      for (const f of data.families) lines.push(`${f.key}\t${pct(a.by_family[f.key])}\t${pct(b.by_family[f.key])}`);
      const n = Math.max(a.by_cycle.length, b.by_cycle.length);
      for (let i = 0; i < n; i++) lines.push(`after compaction ${i + 1}\t${pct(a.by_cycle[i])}\t${pct(b.by_cycle[i])}`);
      return lines.join("\n");
    }
    case "list_families":
      return data.families.map((f) => `${f.key} — ${f.title}: ${f.description}`).join("\n");
    case "explain_metric": {
      const text = METRICS[String(args.metric)];
      return text ?? `Unknown metric. Known: ${Object.keys(METRICS).join(", ")}`;
    }
    default:
      throw new RpcError(-32602, `Unknown tool: ${name}`);
  }
}

class RpcError extends Error {
  code: number;

  constructor(code: number, message: string) {
    super(message);
    this.code = code;
  }
}

/** Handle one JSON-RPC message. Returns null for notifications (no response). */
export function handleMessage(data: Data, message: Json): Json | null {
  const id = message.id;
  const method = String(message.method ?? "");
  if (id === undefined || id === null) return null; // notification, e.g. notifications/initialized
  try {
    const params = (message.params ?? {}) as Json;
    let result: Json;
    if (method === "initialize") {
      const asked = String(params.protocolVersion ?? "");
      result = {
        protocolVersion: SUPPORTED_VERSIONS.includes(asked) ? asked : SUPPORTED_VERSIONS[0],
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "compactbench", version: "1.0.0" },
        instructions:
          "Read-only access to the CompactBench context-compaction leaderboard, methods, families and metric definitions.",
      };
    } else if (method === "ping") {
      result = {};
    } else if (method === "tools/list") {
      result = { tools: TOOLS };
    } else if (method === "tools/call") {
      const text = callTool(data, String(params.name ?? ""), (params.arguments ?? {}) as Json);
      result = { content: [{ type: "text", text }], isError: false };
    } else {
      throw new RpcError(-32601, `Method not found: ${method}`);
    }
    return { jsonrpc: "2.0", id, result };
  } catch (error) {
    const code = error instanceof RpcError ? error.code : -32603;
    return { jsonrpc: "2.0", id, error: { code, message: (error as Error).message } };
  }
}

/** HTTP entry: POST a JSON-RPC message or batch; GET is not offered (no server-sent stream). */
export async function handleHttp(request: Request, load: () => Promise<Data>): Promise<Response> {
  const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type, mcp-protocol-version, mcp-session-id" };
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: { ...cors, "Access-Control-Allow-Methods": "POST, OPTIONS" } });
  if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST", ...cors } });
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }, { status: 400, headers: cors });
  }
  const data = await load();
  const messages = Array.isArray(body) ? body : [body];
  const replies = messages.map((m) => handleMessage(data, (m ?? {}) as Json)).filter((r) => r !== null);
  if (!replies.length) return new Response(null, { status: 202, headers: cors });
  return Response.json(Array.isArray(body) ? replies : replies[0], { headers: cors });
}
