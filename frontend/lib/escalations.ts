// Server-only access to the Day 7 human-help escalations.
//
// The voice agent (backend, Python) writes each request into a SQLite file,
// `backend/escalations.db`. This module lets the Next.js help desk read that
// same file and update a request's status — so the whole thing lives in one app,
// one tab, with no separate dashboard process.
//
// We use `node-sqlite3-wasm` (a no-compile WASM build of SQLite) so it works
// without a native toolchain. It must run on the Node runtime, never the Edge
// runtime — the API route that imports this sets `runtime = 'nodejs'`.
import { existsSync } from 'node:fs';
import path from 'node:path';

import { Database } from 'node-sqlite3-wasm';

export type EscalationStatus = 'open' | 'in_progress' | 'resolved';
export type Urgency = 'low' | 'medium' | 'high' | 'emergency';

export type Escalation = {
  ref_id: string;
  created_at: string;
  updated_at: string;
  caller_name: string;
  reason: string;
  reason_label: string;
  summary: string;
  checked: string;
  urgency: Urgency;
  language: string;
  follow_up: string;
  status: EscalationStatus;
  webhook_sent: number;
};

const STATUSES: EscalationStatus[] = ['open', 'in_progress', 'resolved'];

// Where the agent's SQLite file lives. Override with ESCALATIONS_DB_PATH if you
// run the frontend from somewhere other than the repo's `frontend/` dir.
function dbPath(): string {
  return (
    process.env.ESCALATIONS_DB_PATH ?? path.join(process.cwd(), '..', 'backend', 'escalations.db')
  );
}

// Open the DB, run `fn`, and always close it. Returns `fallback` if the file or
// table doesn't exist yet (i.e. the agent hasn't raised any request), so a fresh
// setup shows an empty help desk instead of a 500.
function withDb<T>(readOnly: boolean, fallback: T, fn: (db: Database) => T): T {
  const file = dbPath();
  // The agent creates the DB the first time it starts. Until then there is
  // simply nothing to show — an empty desk, not an error.
  if (!existsSync(file)) return fallback;

  let db: Database | undefined;
  try {
    db = new Database(file, { readOnly, fileMustExist: true });
    // Don't fail if the agent is mid-write; wait briefly for the lock.
    db.run('PRAGMA busy_timeout = 3000');
    return fn(db);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    // A missing file/table just means "nothing escalated yet" — not an error.
    if (/no such table|unable to open|does not exist|cannot open/i.test(message)) {
      return fallback;
    }
    throw err;
  } finally {
    db?.close();
  }
}

export function listEscalations(status?: string): Escalation[] {
  const filter = STATUSES.includes(status as EscalationStatus) ? status : undefined;
  return withDb<Escalation[]>(true, [], (db) => {
    const sql = filter
      ? 'SELECT * FROM escalations WHERE status = ? ORDER BY created_at DESC'
      : 'SELECT * FROM escalations ORDER BY created_at DESC';
    const rows = filter ? db.all(sql, [filter]) : db.all(sql);
    return rows as unknown as Escalation[];
  });
}

export function openCount(): number {
  return withDb<number>(true, 0, (db) => {
    const row = db.get("SELECT COUNT(*) AS n FROM escalations WHERE status = 'open'");
    return Number((row as { n?: number } | undefined)?.n ?? 0);
  });
}

// Move a request to a new status (the human working the queue). Returns the
// updated row, or null if the ref id or status is invalid.
export function updateStatus(refId: string, status: string): Escalation | null {
  if (!STATUSES.includes(status as EscalationStatus)) return null;
  return withDb<Escalation | null>(false, null, (db) => {
    const now = new Date().toISOString();
    const res = db.run('UPDATE escalations SET status = ?, updated_at = ? WHERE ref_id = ?', [
      status,
      now,
      refId,
    ]);
    if (!res.changes) return null;
    const row = db.get('SELECT * FROM escalations WHERE ref_id = ?', [refId]);
    return (row as unknown as Escalation) ?? null;
  });
}
