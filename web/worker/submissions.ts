// Ranked submissions from the website: validate, seal the keys, apply limits, store,
// and start the evaluation workflow. The rules mirror compactbench.submission so
// both sides accept exactly the same bundles.
import { seal } from "./seal.ts";
import type { Status, Store, SubmissionRecord } from "./store.ts";

export const PROVIDERS = [
  "anthropic", "openai", "groq", "openrouter", "deepseek", "mistral",
  "together", "fireworks", "xai", "gemini", "custom",
] as const;

const PATTERNS = {
  method_name: /^[a-z0-9][a-z0-9._-]{0,63}$/,
  method_version: /^[0-9]+\.[0-9]+\.[0-9]+$/,
  class_name: /^[A-Za-z_][A-Za-z0-9_]{0,63}$/,
  model: /^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$/,
  model_label: /^[A-Za-z0-9][A-Za-z0-9 ._+()/-]{0,47}$/,
  requirement: /^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?==[A-Za-z0-9][A-Za-z0-9.+!_-]*$/,
  key: /^\S{8,400}$/,
};
const MAX_METHOD_BYTES = 200_000;
const MAX_REQUIREMENTS_BYTES = 4_000;
const MAX_CONFIG_BYTES = 16_384;

export interface Limits {
  perUserPerWeek: number;
  globalPerDay: number;
  open: boolean;
}

export interface SubmitInput {
  method_name?: unknown;
  method_version?: unknown;
  class_name?: unknown;
  provider?: unknown;
  model?: unknown;
  base_url?: unknown;
  model_label?: unknown;
  method_config?: unknown;
  method_py?: unknown;
  requirements?: unknown;
  method_key?: unknown;
  reader_key?: unknown;
}

export class SubmitError extends Error {
  status: number;

  constructor(message: string, status = 400) {
    super(message);
    this.status = status;
  }
}

const bytes = (text: string) => new TextEncoder().encode(text).length;
const str = (value: unknown): string => (typeof value === "string" ? value.trim() : "");

function check(field: keyof typeof PATTERNS, value: string, hint: string): string {
  if (!PATTERNS[field].test(value)) throw new SubmitError(`${field}: ${hint}`);
  return value;
}

/** Validate the form; returns the bundle fields other than the keys. Throws SubmitError. */
export function validate(input: SubmitInput) {
  const provider = str(input.provider);
  if (!(PROVIDERS as readonly string[]).includes(provider)) {
    throw new SubmitError(`provider: choose one of ${PROVIDERS.join(", ")}`);
  }
  const methodPy = typeof input.method_py === "string" ? input.method_py : "";
  if (!methodPy.trim()) throw new SubmitError("method.py is empty");
  if (bytes(methodPy) > MAX_METHOD_BYTES) throw new SubmitError("method.py is larger than 200 KB");
  if (methodPy.includes("\u0000")) throw new SubmitError("method.py contains a NUL byte");
  const requirements = typeof input.requirements === "string" ? input.requirements : "";
  if (bytes(requirements) > MAX_REQUIREMENTS_BYTES) throw new SubmitError("requirements are larger than 4 KB");
  for (const raw of requirements.split(/\r?\n/)) {
    const line = raw.trim();
    if (line && !line.startsWith("#") && !PATTERNS.requirement.test(line)) {
      throw new SubmitError(`requirement "${line.slice(0, 60)}" must be pinned as name==version`);
    }
  }
  let config: Record<string, unknown> = {};
  if (input.method_config !== undefined && input.method_config !== null && input.method_config !== "") {
    const parsed = typeof input.method_config === "string" ? safeJson(input.method_config) : input.method_config;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new SubmitError("method_config must be a JSON object");
    }
    config = parsed as Record<string, unknown>;
    if (bytes(JSON.stringify(config)) > MAX_CONFIG_BYTES) throw new SubmitError("method_config is larger than 16 KB");
  }
  const baseUrl = str(input.base_url) || null;
  const label = str(input.model_label) || null;
  if (provider === "custom") {
    if (!baseUrl) throw new SubmitError("base_url: a custom endpoint needs its https:// URL");
    let url: URL;
    try {
      url = new URL(baseUrl);
    } catch {
      throw new SubmitError("base_url: not a valid URL");
    }
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) {
      throw new SubmitError("base_url: must be https:// with no credentials, query or fragment");
    }
    if (label) check("model_label", label, "letters, digits, spaces and . _ + ( ) / - (max 48)");
  } else {
    if (baseUrl) throw new SubmitError("base_url is only for a custom endpoint");
    if (label) throw new SubmitError("a display name is only for a custom endpoint; hosted models keep their id");
  }
  return {
    method_name: check("method_name", str(input.method_name), "lowercase letters, digits, . _ - (max 64)"),
    method_version: check("method_version", str(input.method_version), "semver, e.g. 1.0.0"),
    class_name: check("class_name", str(input.class_name), "a Python class name"),
    provider,
    model: check("model", str(input.model), "the model id your provider expects, no spaces"),
    base_url: baseUrl,
    model_label: label,
    method_config: config,
    method_py: methodPy,
    requirements,
  };
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    throw new SubmitError("method_config must be valid JSON");
  }
}

export function newId(): string {
  const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => alphabet[b % alphabet.length]).join("");
}

export interface SubmitContext {
  store: Store;
  limits: Limits;
  season: string;
  seasonPublicKey: string;
  user: { login: string; id: number };
  dispatch: (id: string) => Promise<boolean>;
  now?: Date;
}

/** Accept a submission. Plain keys are sealed before anything is stored. */
export async function submit(input: SubmitInput, ctx: SubmitContext): Promise<SubmissionRecord> {
  if (!ctx.limits.open) throw new SubmitError("Ranked submissions are paused right now.", 503);
  const fields = validate(input);
  const methodKey = str(input.method_key);
  const readerKey = str(input.reader_key);
  if (fields.provider !== "custom" && !methodKey) throw new SubmitError("method_key: your provider API key is required");
  if (methodKey && !PATTERNS.key.test(methodKey)) throw new SubmitError("method_key doesn't look like an API key");
  if (fields.provider !== "anthropic" && !readerKey) {
    throw new SubmitError("reader_key: an Anthropic API key is required to pay for grading");
  }
  if (readerKey && !PATTERNS.key.test(readerKey)) throw new SubmitError("reader_key doesn't look like an API key");

  const now = ctx.now ?? new Date();
  const weekAgo = new Date(now.getTime() - 7 * 86_400_000).toISOString();
  const dayAgo = new Date(now.getTime() - 86_400_000).toISOString();
  if ((await ctx.store.activeForUser(ctx.user.id)) > 0) {
    throw new SubmitError("You already have a run in progress; wait for it to finish.", 429);
  }
  if ((await ctx.store.countForUserSince(ctx.user.id, weekAgo)) >= ctx.limits.perUserPerWeek) {
    throw new SubmitError(`At most ${ctx.limits.perUserPerWeek} ranked runs per week per account.`, 429);
  }
  if ((await ctx.store.countSince(dayAgo)) >= ctx.limits.globalPerDay) {
    throw new SubmitError("Today's ranked run capacity is used up; try again tomorrow.", 429);
  }

  const id = newId();
  const created = now.toISOString();
  const bundle = {
    id,
    season: ctx.season,
    handle: ctx.user.login,
    github_id: ctx.user.id,
    ...fields,
    sealed_method_key: methodKey ? await seal(ctx.seasonPublicKey, methodKey, `key:${ctx.season}:${id}`) : null,
    sealed_reader_key: readerKey ? await seal(ctx.seasonPublicKey, readerKey, `reader:${ctx.season}:${id}`) : null,
    created_at: created,
  };
  const record: SubmissionRecord = {
    id,
    github_id: ctx.user.id,
    handle: ctx.user.login,
    method_name: fields.method_name,
    method_version: fields.method_version,
    provider: fields.provider,
    model: fields.model,
    model_label: fields.model_label,
    status: "queued",
    message: null,
    score: null,
    created_at: created,
    updated_at: created,
  };
  await ctx.store.insert(record, JSON.stringify(bundle));
  if (!(await ctx.dispatch(id))) {
    await ctx.store.update(id, { status: "failed", message: "Couldn't start the evaluation; please try again later." });
    record.status = "failed";
  }
  return record;
}

/** What anyone with the link may see about a submission: no keys, no code. */
export function publicView(record: SubmissionRecord) {
  const { github_id: _github, ...rest } = record;
  return rest;
}

export const REPORTABLE: Status[] = ["building", "running", "published", "failed", "rejected"];
