// Where submissions live: a D1 table for status and rate limits, R2 for bundles, and a
// separate private R2 bucket for each finished run's sealed files.
// The interface keeps the logic testable without Cloudflare.

import type { ContactWindow } from "./contact.ts";

export type Status = "queued" | "building" | "running" | "published" | "failed" | "rejected";
export const ACTIVE: Status[] = ["queued", "building", "running"];
/** A run still active with no update for this long has stopped reporting (the longest
 *  legitimate gap is the evaluate job's 5-hour limit plus publishing and queueing). */
export const STALE_AFTER_MS = 8 * 3600_000;
export const STALE_MESSAGE =
  "This run stopped without reporting back, so it was closed. Nothing was published; you can submit again.";

/** Why a submission wasn't stored: a run in progress, the weekly per-account cap, or the
 *  global daily cap. */
export type LimitOutcome = "ok" | "active" | "week" | "day";
export interface LimitWindow {
  weekSince: string;
  perWeek: number;
  daySince: string;
  perDay: number;
}

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
  /** Store a new submission only if the account has no run in progress and both caps have
   *  room, checked and inserted in one step so parallel requests can't all pass. */
  insertWithinLimits(record: SubmissionRecord, bundle: string, limits: LimitWindow): Promise<LimitOutcome>;
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
  /** Close active runs not updated since `before` as failed, so their submitter isn't locked
   *  out. Returns how many were closed. */
  expireStale(before: string, message: string): Promise<number>;
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

  async insertWithinLimits(r: SubmissionRecord, bundle: string, l: LimitWindow): Promise<LimitOutcome> {
    // One statement: D1 runs it atomically, so a burst of parallel requests is serialized here
    // and only the ones that still fit are inserted.
    const result = (await this.db
      .prepare(
        `INSERT INTO submissions (id, github_id, handle, method_name, method_version, provider, model,
          model_label, status, message, score, created_at, updated_at)
         SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
         WHERE NOT EXISTS (SELECT 1 FROM submissions WHERE github_id = ? AND status IN ('queued','building','running'))
           AND (SELECT COUNT(*) FROM submissions WHERE github_id = ? AND created_at >= ? AND status != 'rejected') < ?
           AND (SELECT COUNT(*) FROM submissions WHERE created_at >= ? AND status != 'rejected') < ?`,
      )
      .bind(
        r.id, r.github_id, r.handle, r.method_name, r.method_version, r.provider, r.model,
        r.model_label, r.status, r.message, r.score, r.created_at, r.updated_at,
        r.github_id, r.github_id, l.weekSince, l.perWeek, l.daySince, l.perDay,
      )
      .run()) as { meta?: { changes?: number } } | null;
    if ((result?.meta?.changes ?? 0) !== 1) {
      if ((await this.activeForUser(r.github_id)) > 0) return "active";
      if ((await this.countForUserSince(r.github_id, l.weekSince)) >= l.perWeek) return "week";
      return "day";
    }
    try {
      await this.bucket.put(`bundles/${r.id}.json`, bundle);
    } catch (error) {
      await this.db.prepare("DELETE FROM submissions WHERE id = ?").bind(r.id).run();
      throw error;
    }
    return "ok";
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

  async expireStale(before: string, message: string): Promise<number> {
    const result = (await this.db
      .prepare(
        `UPDATE submissions SET status = 'failed', message = ?, updated_at = ?
           WHERE status IN ('queued','building','running') AND updated_at < ?`,
      )
      .bind(message, new Date().toISOString(), before)
      .run()) as { meta?: { changes?: number } } | null;
    return result?.meta?.changes ?? 0;
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
  async insertWithinLimits(r: SubmissionRecord, bundle: string, l: LimitWindow): Promise<LimitOutcome> {
    // No await between the checks and the insert, so parallel calls can't interleave.
    const all = [...this.records.values()];
    if (all.some((x) => x.github_id === r.github_id && ACTIVE.includes(x.status))) return "active";
    const week = all.filter((x) => x.github_id === r.github_id && x.created_at >= l.weekSince && x.status !== "rejected");
    if (week.length >= l.perWeek) return "week";
    if (all.filter((x) => x.created_at >= l.daySince && x.status !== "rejected").length >= l.perDay) return "day";
    this.records.set(r.id, { ...r });
    this.bundles.set(r.id, bundle);
    return "ok";
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
  async expireStale(before: string, message: string): Promise<number> {
    let closed = 0;
    for (const r of this.records.values()) {
      if (ACTIVE.includes(r.status) && r.updated_at < before) {
        Object.assign(r, { status: "failed", message, updated_at: new Date().toISOString() });
        closed++;
      }
    }
    return closed;
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
  async reserve(ipHash: string, at: string, l: ContactWindow): Promise<"ok" | "sender" | "global"> {
    // One statement, so D1 runs the checks and the insert atomically.
    const result = (await this.db
      .prepare(
        `INSERT INTO contact_log (ip_hash, at) SELECT ?, ?
           WHERE (SELECT COUNT(*) FROM contact_log WHERE ip_hash = ? AND at >= ?) < ?
             AND (SELECT COUNT(*) FROM contact_log WHERE at >= ?) < ?`,
      )
      .bind(ipHash, at, ipHash, l.hourSince, l.perSender, l.daySince, l.perDay)
      .run()) as { meta?: { changes?: number } } | null;
    if ((result?.meta?.changes ?? 0) === 1) return "ok";
    return (await this.countSince(ipHash, l.hourSince)) >= l.perSender ? "sender" : "global";
  }
  async release(ipHash: string, at: string): Promise<void> {
    await this.db
      .prepare("DELETE FROM contact_log WHERE rowid = (SELECT rowid FROM contact_log WHERE ip_hash = ? AND at = ? LIMIT 1)")
      .bind(ipHash, at)
      .run();
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
