// Where submissions live: a D1 table for status and rate limits, R2 for bundles, and a
// separate private R2 bucket for each finished run's sealed files.
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
  /** Forget a submission that never started: its record and its bundle (sealed keys). */
  remove(id: string): Promise<void>;
  /** One account's submissions, newest first. */
  listForUser(githubId: number, limit: number): Promise<SubmissionRecord[]>;
  /** Keep one of a finished run's files (sealed traces and results, commitment) privately. */
  archive(season: string, id: string, name: string, body: ArrayBuffer): Promise<void>;
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
  put(key: string, value: string | ArrayBuffer): Promise<unknown>;
  get(key: string): Promise<{ text(): Promise<string> } | null>;
  delete(key: string): Promise<unknown>;
}

export class CloudflareStore implements Store {
  db: D1;
  bucket: R2;
  archiveBucket: R2 | undefined;

  constructor(db: D1, bucket: R2, archiveBucket?: R2) {
    this.db = db;
    this.bucket = bucket;
    this.archiveBucket = archiveBucket;
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

  async remove(id: string): Promise<void> {
    await this.db.prepare("DELETE FROM submissions WHERE id = ?").bind(id).run();
    await this.bucket.delete(`bundles/${id}.json`);
  }

  async archive(season: string, id: string, name: string, body: ArrayBuffer): Promise<void> {
    if (!this.archiveBucket) throw new Error("no archive bucket is bound");
    await this.archiveBucket.put(archiveKey(season, id, name), body);
  }

  async listForUser(githubId: number, limit: number): Promise<SubmissionRecord[]> {
    const rows = await this.db
      .prepare("SELECT * FROM submissions WHERE github_id = ? ORDER BY created_at DESC LIMIT ?")
      .bind(githubId, limit)
      .all<SubmissionRecord>();
    return rows.results;
  }
}

/** Where a run's file sits in the archive bucket. */
export const archiveKey = (season: string, id: string, name: string) => `runs/${season}/${id}/${name}`;

/** In-memory store for tests and local development. */
export class MemoryStore implements Store {
  records = new Map<string, SubmissionRecord>();
  bundles = new Map<string, string>();
  archived = new Map<string, ArrayBuffer>();

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
  async remove(id: string): Promise<void> {
    this.records.delete(id);
    this.bundles.delete(id);
  }
  async archive(season: string, id: string, name: string, body: ArrayBuffer): Promise<void> {
    this.archived.set(archiveKey(season, id, name), body);
  }
  async listForUser(githubId: number, limit: number): Promise<SubmissionRecord[]> {
    return [...this.records.values()]
      .filter((r) => r.github_id === githubId)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, limit)
      .map((r) => ({ ...r }));
  }
}

/** Contact-form rate limits in D1: keyed IP hashes and times, pruned after a day. */
export class D1ContactLog {
  private db: D1;

  constructor(db: D1) {
    this.db = db;
  }

  async countSince(ipHash: string | null, since: string): Promise<number> {
    const row = ipHash === null
      ? await this.db.prepare("SELECT COUNT(*) AS n FROM contact_log WHERE at >= ?").bind(since).first<{ n: number }>()
      : await this.db.prepare("SELECT COUNT(*) AS n FROM contact_log WHERE ip_hash = ? AND at >= ?").bind(ipHash, since).first<{ n: number }>();
    return row?.n ?? 0;
  }
  async record(ipHash: string, at: string): Promise<void> {
    await this.db.prepare("INSERT INTO contact_log (ip_hash, at) VALUES (?, ?)").bind(ipHash, at).run();
  }
  async prune(before: string): Promise<void> {
    await this.db.prepare("DELETE FROM contact_log WHERE at < ?").bind(before).run();
  }
}

const REFERENCE_NAMES = ["sectioned-summary", "hierarchical-summary", "naive-summary", "structured-state"];

/** Report counters and snapshots in D1 (migration 0003). Totals only. */
export class D1StatsStore {
  private db: D1;

  constructor(db: D1) {
    this.db = db;
  }

  async bump(day: string, event: string, by = 1): Promise<void> {
    await this.db
      .prepare("INSERT INTO daily_events (day, event, n) VALUES (?, ?, ?) ON CONFLICT(day, event) DO UPDATE SET n = n + excluded.n")
      .bind(day, event, by)
      .run();
  }
  async events(day: string): Promise<Record<string, number>> {
    const rows = await this.db.prepare("SELECT event, n FROM daily_events WHERE day = ?").bind(day).all<{ event: string; n: number }>();
    return Object.fromEntries(rows.results.map((r) => [r.event, r.n]));
  }
  async eventTotal(prefix: string): Promise<number> {
    const row = await this.db
      .prepare("SELECT COALESCE(SUM(n), 0) AS n FROM daily_events WHERE substr(event, 1, ?) = ?")
      .bind(prefix.length, prefix)
      .first<{ n: number }>();
    return row?.n ?? 0;
  }
  async saveSnapshot(day: string, values: Record<string, number>): Promise<void> {
    for (const [key, value] of Object.entries(values)) {
      await this.db.prepare("INSERT OR REPLACE INTO daily_snapshots (day, key, value) VALUES (?, ?, ?)").bind(day, key, value).run();
    }
  }
  async snapshot(day: string): Promise<Record<string, number>> {
    const rows = await this.db.prepare("SELECT key, value FROM daily_snapshots WHERE day = ?").bind(day).all<{ key: string; value: number }>();
    return Object.fromEntries(rows.results.map((r) => [r.key, r.value]));
  }
  async milestones(): Promise<Set<string>> {
    const rows = await this.db.prepare("SELECT key FROM milestones").all<{ key: string }>();
    return new Set(rows.results.map((r) => r.key));
  }
  async recordMilestone(key: string, day: string): Promise<void> {
    await this.db.prepare("INSERT OR IGNORE INTO milestones (key, day) VALUES (?, ?)").bind(key, day).run();
  }
  async submissions(from: string, to: string) {
    const fresh = await this.db
      .prepare("SELECT status, COUNT(*) AS n FROM submissions WHERE created_at >= ? AND created_at < ? GROUP BY status")
      .bind(from, to)
      .all<{ status: string; n: number }>();
    const totals = await this.db
      .prepare(
        `SELECT COUNT(*) AS total, SUM(status = 'published') AS published, COUNT(DISTINCT github_id) AS people,
         SUM(method_name IN (${REFERENCE_NAMES.map(() => "?").join(", ")})) AS reference_runs FROM submissions`,
      )
      .bind(...REFERENCE_NAMES)
      .first<{ total: number; published: number | null; people: number; reference_runs: number | null }>();
    return {
      newByStatus: Object.fromEntries(fresh.results.map((r) => [r.status, r.n])),
      total: totals?.total ?? 0,
      published: totals?.published ?? 0,
      people: totals?.people ?? 0,
      referenceRuns: totals?.reference_runs ?? 0,
    };
  }
}
