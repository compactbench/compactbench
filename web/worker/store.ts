// Where submissions live: a D1 table for status and rate limits, R2 for bundles.
// The interface keeps the logic testable without Cloudflare.

export type Status = "queued" | "building" | "running" | "published" | "failed" | "rejected";
export const ACTIVE: Status[] = ["queued", "building", "running"];

export interface SubmissionRecord {
  id: string;
  github_id: number;
  handle: string;
  method_name: string;
  method_version: string;
  provider: string;
  model: string;
  model_label: string | null;
  status: Status;
  message: string | null;
  score: number | null;
  created_at: string;
  updated_at: string;
}

export interface Store {
  insert(record: SubmissionRecord, bundle: string): Promise<void>;
  get(id: string): Promise<SubmissionRecord | null>;
  update(id: string, fields: Partial<Pick<SubmissionRecord, "status" | "message" | "score">>): Promise<void>;
  countForUserSince(githubId: number, since: string): Promise<number>;
  activeForUser(githubId: number): Promise<number>;
  countSince(since: string): Promise<number>;
  getBundle(id: string): Promise<string | null>;
  /** One account's submissions, newest first. */
  listForUser(githubId: number, limit: number): Promise<SubmissionRecord[]>;
}

// Minimal shapes of the Cloudflare bindings we use.
interface D1Statement {
  bind(...values: unknown[]): D1Statement;
  first<T>(): Promise<T | null>;
  all<T>(): Promise<{ results: T[] }>;
  run(): Promise<unknown>;
}
export interface D1 {
  prepare(sql: string): D1Statement;
}
export interface R2 {
  put(key: string, value: string): Promise<unknown>;
  get(key: string): Promise<{ text(): Promise<string> } | null>;
}

export class CloudflareStore implements Store {
  db: D1;
  bucket: R2;

  constructor(db: D1, bucket: R2) {
    this.db = db;
    this.bucket = bucket;
  }

  async insert(r: SubmissionRecord, bundle: string): Promise<void> {
    await this.bucket.put(`bundles/${r.id}.json`, bundle);
    await this.db
      .prepare(
        `INSERT INTO submissions (id, github_id, handle, method_name, method_version, provider, model,
          model_label, status, message, score, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(r.id, r.github_id, r.handle, r.method_name, r.method_version, r.provider, r.model,
        r.model_label, r.status, r.message, r.score, r.created_at, r.updated_at)
      .run();
  }

  get(id: string): Promise<SubmissionRecord | null> {
    return this.db.prepare("SELECT * FROM submissions WHERE id = ?").bind(id).first<SubmissionRecord>();
  }

  async update(id: string, fields: Partial<Pick<SubmissionRecord, "status" | "message" | "score">>): Promise<void> {
    await this.db
      .prepare(
        `UPDATE submissions SET status = COALESCE(?, status), message = COALESCE(?, message),
           score = COALESCE(?, score), updated_at = ? WHERE id = ?`,
      )
      .bind(fields.status ?? null, fields.message ?? null, fields.score ?? null, new Date().toISOString(), id)
      .run();
  }

  async countForUserSince(githubId: number, since: string): Promise<number> {
    const row = await this.db
      .prepare("SELECT COUNT(*) AS n FROM submissions WHERE github_id = ? AND created_at >= ? AND status != 'rejected'")
      .bind(githubId, since)
      .first<{ n: number }>();
    return row?.n ?? 0;
  }

  async activeForUser(githubId: number): Promise<number> {
    const row = await this.db
      .prepare("SELECT COUNT(*) AS n FROM submissions WHERE github_id = ? AND status IN ('queued','building','running')")
      .bind(githubId)
      .first<{ n: number }>();
    return row?.n ?? 0;
  }

  async countSince(since: string): Promise<number> {
    const row = await this.db
      .prepare("SELECT COUNT(*) AS n FROM submissions WHERE created_at >= ? AND status != 'rejected'")
      .bind(since)
      .first<{ n: number }>();
    return row?.n ?? 0;
  }

  async getBundle(id: string): Promise<string | null> {
    const object = await this.bucket.get(`bundles/${id}.json`);
    return object ? object.text() : null;
  }

  async listForUser(githubId: number, limit: number): Promise<SubmissionRecord[]> {
    const rows = await this.db
      .prepare("SELECT * FROM submissions WHERE github_id = ? ORDER BY created_at DESC LIMIT ?")
      .bind(githubId, limit)
      .all<SubmissionRecord>();
    return rows.results;
  }
}

/** In-memory store for tests and local development. */
export class MemoryStore implements Store {
  records = new Map<string, SubmissionRecord>();
  bundles = new Map<string, string>();

  async insert(record: SubmissionRecord, bundle: string): Promise<void> {
    this.records.set(record.id, { ...record });
    this.bundles.set(record.id, bundle);
  }
  async get(id: string): Promise<SubmissionRecord | null> {
    return this.records.get(id) ?? null;
  }
  async update(id: string, fields: Partial<Pick<SubmissionRecord, "status" | "message" | "score">>): Promise<void> {
    const record = this.records.get(id);
    if (record) Object.assign(record, Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined)));
  }
  async countForUserSince(githubId: number, since: string): Promise<number> {
    return [...this.records.values()].filter((r) => r.github_id === githubId && r.created_at >= since && r.status !== "rejected").length;
  }
  async activeForUser(githubId: number): Promise<number> {
    return [...this.records.values()].filter((r) => r.github_id === githubId && ACTIVE.includes(r.status)).length;
  }
  async countSince(since: string): Promise<number> {
    return [...this.records.values()].filter((r) => r.created_at >= since && r.status !== "rejected").length;
  }
  async getBundle(id: string): Promise<string | null> {
    return this.bundles.get(id) ?? null;
  }
  async listForUser(githubId: number, limit: number): Promise<SubmissionRecord[]> {
    return [...this.records.values()]
      .filter((r) => r.github_id === githubId)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, limit)
      .map((r) => ({ ...r }));
  }
}
