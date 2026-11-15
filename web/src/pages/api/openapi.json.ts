import type { APIRoute } from "astro";
import { families } from "../../lib/data";

// OpenAPI 3.1 description of the public, read-only API. No key, no sign-up.
const json = (ref: string, description: string) => ({
  description,
  content: { "application/json": { schema: { $ref: `#/components/schemas/${ref}` } } },
});
const rate = { type: "number", minimum: 0, maximum: 1 };

const spec = {
  openapi: "3.1.0",
  info: {
    title: "CompactBench API",
    version: "1.0.0",
    summary: "Leaderboard data for the CompactBench context-compaction benchmark.",
    description:
      "Static, read-only JSON and CSV, rebuilt whenever the leaderboard changes. Scores are fractions in [0, 1]. Licensed Apache 2.0.",
    license: { name: "Apache-2.0", identifier: "Apache-2.0" },
  },
  servers: [{ url: "https://compactbench.com" }],
  paths: {
    "/api/leaderboard.json": {
      get: { operationId: "getLeaderboard", summary: "Every published row", responses: { "200": json("Leaderboard", "The leaderboard") } },
    },
    "/api/leaderboard.csv": {
      get: {
        operationId: "getLeaderboardCsv",
        summary: "The leaderboard as CSV, one column per family",
        responses: { "200": { description: "CSV", content: { "text/csv": { schema: { type: "string" } } } } },
      },
    },
    "/api/methods/{slug}.json": {
      get: {
        operationId: "getMethod",
        summary: "One row by slug (as in /methods/<slug>)",
        parameters: [{ name: "slug", in: "path", required: true, schema: { type: "string", pattern: "^[a-z0-9.-]+$" } }],
        responses: { "200": json("Method", "The row"), "404": { description: "No such row" } },
      },
    },
    "/api/badges/{slug}.json": {
      get: {
        operationId: "getBadge",
        summary: "A shields.io endpoint badge for one row (https://img.shields.io/endpoint?url=…)",
        parameters: [{ name: "slug", in: "path", required: true, schema: { type: "string", pattern: "^[a-z0-9.-]+$" } }],
        responses: { "200": { description: "shields.io endpoint JSON", content: { "application/json": { schema: { type: "object" } } } } },
      },
    },
    "/api/families.json": {
      get: {
        operationId: "listFamilies",
        summary: "The failure families",
        responses: { "200": { description: "Families", content: { "application/json": { schema: { type: "array", items: { $ref: "#/components/schemas/Family" } } } } } },
      },
    },
    "/api/season.json": {
      get: { operationId: "getSeason", summary: "The current season's pinned settings", responses: { "200": { description: "Season", content: { "application/json": { schema: { type: "object" } } } } } },
    },
    "/api/submissions/{id}": {
      get: {
        operationId: "getSubmissionStatus",
        summary: "Status of a ranked run (public; no keys or code)",
        parameters: [{ name: "id", in: "path", required: true, schema: { type: "string", pattern: "^[a-z0-9]{12,32}$" } }],
        responses: { "200": json("SubmissionStatus", "The run"), "404": { description: "No such run" } },
      },
    },
    "/mcp": {
      post: {
        operationId: "mcp",
        summary: "Remote MCP server (Streamable HTTP, JSON-RPC 2.0, read-only tools)",
        requestBody: { required: true, content: { "application/json": { schema: { type: "object" } } } },
        responses: { "200": { description: "JSON-RPC response" }, "202": { description: "Notification accepted" } },
      },
    },
  },
  components: {
    schemas: {
      Leaderboard: {
        type: "object",
        required: ["updated_at", "entries"],
        properties: { updated_at: { type: "string", format: "date-time" }, entries: { type: "array", items: { $ref: "#/components/schemas/Row" } } },
      },
      Method: { allOf: [{ $ref: "#/components/schemas/Row" }, { type: "object", properties: { slug: { type: "string" }, url: { type: "string", format: "uri" } } }] },
      Row: {
        type: "object",
        description: "One published result. Ranks are CI-aware: rows whose 95% intervals overlap share a rank.",
        properties: {
          rank: { type: ["integer", "null"], description: "Rank on the method board; null for baselines, controls and model rows" },
          reference_method: {
            type: ["string", "null"],
            description: "Set when the row ran this published built-in unchanged on its model: the By model board",
          },
          model_rank: { type: ["integer", "null"], description: "Rank among models on the same reference_method" },
          row_kind: { enum: ["submission", "baseline", "control"] },
          method_name: { type: "string" },
          method_version: { type: "string" },
          handle: { type: ["string", "null"], description: "GitHub handle of the submitter" },
          org: { type: ["string", "null"] },
          suite: { type: "string" },
          season: { type: ["string", "null"] },
          scorer_version: { type: "string" },
          reader_provider: { type: "string" },
          reader_model: { type: "string" },
          reader_effort: { type: ["string", "null"] },
          compactor_provider: { type: "string" },
          compactor_model: { type: "string" },
          compactor_endpoint_kind: { type: "string", description: "'custom' for a submitter's own endpoint" },
          model_label: { type: ["string", "null"], description: "Display name for a custom-endpoint model" },
          budget_tokens: { type: ["integer", "null"] },
          score: { ...rate, description: "Family-balanced score" },
          score_ci_low: rate,
          score_ci_high: rate,
          normalized_score: { type: ["number", "null"] },
          drift_resistance: { type: "number" },
          stale_rate: rate,
          trap_rate: rate,
          hallucination_rate: rate,
          mean_artifact_tokens: { type: "number" },
          compression_ratio: { type: "number" },
          method_tokens: { type: ["number", "null"] },
          by_family: { type: "object", additionalProperties: rate, propertyNames: { enum: families.map((f) => f.key) } },
          by_cycle: { type: "array", items: rate, description: "Score after each compaction" },
          cases: { type: "integer" },
          published_at: { type: "string", format: "date-time" },
        },
      },
      Family: { type: "object", properties: { key: { type: "string" }, title: { type: "string" }, description: { type: "string" } } },
      SubmissionStatus: {
        type: "object",
        properties: {
          id: { type: "string" },
          status: { enum: ["queued", "building", "running", "published", "failed", "rejected"] },
          message: { type: ["string", "null"] },
          score: { type: ["number", "null"] },
          handle: { type: "string" },
          method_name: { type: "string" },
          method_version: { type: "string" },
          provider: { type: "string" },
          model: { type: "string" },
          model_label: { type: ["string", "null"] },
          created_at: { type: "string", format: "date-time" },
          updated_at: { type: "string", format: "date-time" },
        },
      },
    },
  },
};

export const GET: APIRoute = () =>
  new Response(JSON.stringify(spec, null, 2), { headers: { "Content-Type": "application/json; charset=utf-8" } });
