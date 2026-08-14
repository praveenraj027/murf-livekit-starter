// Server-only access to the Day 8 call analytics.
//
// The voice agent (backend, Python) records the outcome of every call into a
// SQLite file, `backend/call_analytics.db`. This module lets the Next.js app
// read that same file and compute the dashboard numbers — so the analytics live
// in the app itself, one tab, no separate Python dashboard process.
//
// Mirrors `lib/escalations.ts`: `node-sqlite3-wasm` (a no-compile WASM build of
// SQLite) on the Node runtime only. The API route that imports this must set
// `runtime = 'nodejs'`.
//
// Privacy: the store keeps no caller name, phone number, transcript, OTP, PIN,
// or account number — only the room id, channel, timestamps, duration, and a
// coarse outcome reason. There is nothing sensitive to read here.
import { Database } from 'node-sqlite3-wasm';
import { existsSync } from 'node:fs';
import path from 'node:path';

export type CallOutcome = 'in_progress' | 'success' | 'failed';

export type CallRow = {
  call_id: string;
  channel: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  outcome: CallOutcome;
  success_reason: string;
  failure_reason: string;
};

export type ChannelBucket = { total: number; successful: number; failed: number };

export type Stats = {
  total: number; // ended calls only, so total === successful + failed
  successful: number;
  failed: number;
  active: number; // live/in-progress, reported separately (never in total)
  success_rate: number; // 0–100
  by_channel: Record<string, ChannelBucket>;
  by_failure: Record<string, number>;
  by_success: Record<string, number>;
};

// Where the agent's SQLite file lives. Override with CALL_ANALYTICS_DB_PATH if
// you run the frontend from somewhere other than the repo's `frontend/` dir.
function dbPath(): string {
  return (
    process.env.CALL_ANALYTICS_DB_PATH ??
    path.join(process.cwd(), '..', 'backend', 'call_analytics.db')
  );
}

// Open the DB, run `fn`, and always close it. Returns `fallback` if the file or
// table doesn't exist yet (the agent hasn't recorded a call), so a fresh setup
// shows an empty dashboard instead of a 500.
function withDb<T>(fallback: T, fn: (db: Database) => T): T {
  const file = dbPath();
  if (!existsSync(file)) return fallback;

  let db: Database | undefined;
  try {
    db = new Database(file, { readOnly: true, fileMustExist: true });
    // Don't fail if the agent is mid-write; wait briefly for the lock.
    db.run('PRAGMA busy_timeout = 3000');
    return fn(db);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    // A missing file/table just means "no calls recorded yet" — not an error.
    if (/no such table|unable to open|does not exist|cannot open/i.test(message)) {
      return fallback;
    }
    throw err;
  } finally {
    db?.close();
  }
}

const EMPTY_STATS: Stats = {
  total: 0,
  successful: 0,
  failed: 0,
  active: 0,
  success_rate: 0,
  by_channel: {},
  by_failure: {},
  by_success: {},
};

function countWhere(db: Database, where: string): number {
  const row = db.get(`SELECT COUNT(*) AS n FROM calls WHERE ${where}`) as
    | { n?: number }
    | undefined;
  return Number(row?.n ?? 0);
}

// The same numbers the Python dashboard computes: total counts only ended calls,
// so it always equals successful + failed; live calls are reported as `active`.
export function getStats(): Stats {
  return withDb<Stats>(EMPTY_STATS, (db) => {
    const successful = countWhere(db, "outcome = 'success'");
    const failed = countWhere(db, "outcome = 'failed'");
    const active = countWhere(db, "outcome = 'in_progress'");

    const by_channel: Record<string, ChannelBucket> = {};
    for (const r of db.all(
      "SELECT channel, outcome, COUNT(*) AS n FROM calls WHERE outcome != 'in_progress' GROUP BY channel, outcome"
    ) as unknown as Array<{ channel: string; outcome: string; n: number }>) {
      const b = (by_channel[r.channel] ??= { total: 0, successful: 0, failed: 0 });
      b.total += r.n;
      if (r.outcome === 'success') b.successful += r.n;
      else if (r.outcome === 'failed') b.failed += r.n;
    }

    const groupReason = (outcome: string, col: string): Record<string, number> => {
      const out: Record<string, number> = {};
      for (const r of db.all(
        `SELECT ${col} AS reason, COUNT(*) AS n FROM calls WHERE outcome = '${outcome}' GROUP BY ${col} ORDER BY n DESC`
      ) as unknown as Array<{ reason: string | null; n: number }>) {
        out[r.reason || 'unknown'] = r.n;
      }
      return out;
    };

    const total = successful + failed;
    const success_rate = total ? Math.round((successful / total) * 1000) / 10 : 0;
    return {
      total,
      successful,
      failed,
      active,
      success_rate,
      by_channel,
      by_failure: groupReason('failed', 'failure_reason'),
      by_success: groupReason('success', 'success_reason'),
    };
  });
}

// Recent calls, newest first, for the passbook history. Non-sensitive fields only.
export function recentCalls(limit = 25): CallRow[] {
  return withDb<CallRow[]>([], (db) => {
    const rows = db.all('SELECT * FROM calls ORDER BY started_at DESC LIMIT ?', [limit]);
    return rows as unknown as CallRow[];
  });
}
