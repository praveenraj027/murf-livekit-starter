'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

// ---- Types (mirror /api/analytics) ------------------------------------------
type Outcome = 'in_progress' | 'success' | 'failed';
type ChannelBucket = { total: number; successful: number; failed: number };
type Stats = {
  total: number;
  successful: number;
  failed: number;
  active: number;
  success_rate: number;
  by_channel: Record<string, ChannelBucket>;
  by_failure: Record<string, number>;
  by_success: Record<string, number>;
};
type CallRow = {
  call_id: string;
  channel: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  outcome: Outcome;
  success_reason: string;
  failure_reason: string;
};

const CHANNEL_LABEL: Record<string, string> = { browser: 'Browser', phone: 'Phone' };
const FAILURE_LABEL: Record<string, string> = {
  incomplete: 'Ended before success',
  no_answer: 'No answer',
  busy: 'Busy',
  declined: 'Declined',
  dial_failed: 'Dial failed',
  error: 'Tool / API error',
  unknown: 'Unknown',
};
const SUCCESS_LABEL: Record<string, string> = {
  eligibility_check: 'Eligibility / documents',
  human_escalation: 'Human help raised',
  unknown: 'Success',
};

// ---- Small formatting helpers ----------------------------------------------
function fmtDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—';
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`;
}
function fmtTime(iso: string): string {
  // "2026-08-14T10:32:05+00:00" -> "10:32"
  const t = iso.includes('T') ? iso.split('T')[1] : iso;
  return t ? t.slice(0, 5) : '—';
}
function fmtDate(iso: string): string {
  return iso.includes('T') ? iso.split('T')[0] : iso;
}

// Count a figure up to its target when the target changes — a small, honest bit
// of motion so a new call visibly ticks the number up on screen. Respects
// reduced-motion by snapping straight to the value.
function useCountUp(target: number, duration = 600): number {
  const [display, setDisplay] = useState(target);
  const fromRef = useRef(target);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const from = fromRef.current;
    if (reduce || from === target) {
      fromRef.current = target;
      setDisplay(target);
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
      setDisplay(Math.round(from + (target - from) * eased));
      if (p < 1) rafRef.current = requestAnimationFrame(tick);
      else fromRef.current = target;
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [target, duration]);

  return display;
}

// ---- Building blocks --------------------------------------------------------
function StatCard({
  label,
  value,
  accent,
  sub,
}: {
  label: string;
  value: number;
  accent: string; // border-top color class
  sub: string;
}) {
  const shown = useCountUp(value);
  return (
    <div
      className={`bg-card border-border/70 relative flex-1 overflow-hidden rounded-xl border p-5 shadow-sm md:p-6 ${accent}`}
    >
      <div className="text-muted-foreground font-mono text-[10px] font-medium tracking-[0.2em] uppercase">
        {label}
      </div>
      <div className="text-foreground mt-2 font-mono text-5xl font-bold tabular-nums md:text-6xl">
        {shown}
      </div>
      <div className="text-muted-foreground mt-1.5 text-xs">{sub}</div>
    </div>
  );
}

function MiniList({
  title,
  entries,
  labels,
  barClass,
}: {
  title: string;
  entries: Record<string, number>;
  labels: Record<string, string>;
  barClass: string;
}) {
  const rows = Object.entries(entries);
  const total = rows.reduce((n, [, v]) => n + v, 0);
  return (
    <div className="bg-card border-border/70 flex-1 rounded-xl border p-5">
      <h3 className="text-foreground mb-3 font-serif text-base">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-muted-foreground text-xs">Nothing yet.</p>
      ) : (
        <div className="space-y-2.5">
          {rows.map(([key, n]) => (
            <div key={key}>
              <div className="text-foreground/90 mb-1 flex justify-between text-[13px]">
                <span>{labels[key] ?? key}</span>
                <span className="font-mono tabular-nums">{n}</span>
              </div>
              <div className="bg-muted h-1.5 overflow-hidden rounded-full">
                <div
                  className={`h-full rounded-full transition-[width] duration-700 ease-out ${barClass}`}
                  style={{ width: total ? `${(n / total) * 100}%` : '0%' }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function OutcomePill({ outcome }: { outcome: Outcome }) {
  const map: Record<Outcome, string> = {
    success: 'text-brass border-brass/40 bg-brass/10',
    failed: 'text-destructive border-destructive/40 bg-destructive/10',
    in_progress: 'text-muted-foreground border-border bg-muted',
  };
  const label = outcome === 'in_progress' ? 'live' : outcome;
  return (
    <span
      className={`rounded-full border px-2.5 py-0.5 font-mono text-[10px] font-medium tracking-wide uppercase ${map[outcome]}`}
    >
      {label}
    </span>
  );
}

// ---- Page -------------------------------------------------------------------
export default function AnalyticsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [calls, setCalls] = useState<CallRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [barWidth, setBarWidth] = useState(0); // success-rate bar, animated from 0

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/analytics', { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setStats(data.stats);
      setCalls(data.calls ?? []);
      setError(null);
    } catch {
      setError('Could not reach the analytics store. Is the agent’s backend running?');
    }
  }, []);

  // Poll every 3s so a call's outcome appears without a manual refresh.
  useEffect(() => {
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [load]);

  // Let the success-rate bar draw across to its live value.
  useEffect(() => {
    if (stats) setBarWidth(stats.success_rate);
  }, [stats]);

  return (
    <main className="mx-auto max-w-3xl px-5 pt-24 pb-16 md:px-8">
      {/* Header */}
      <div className="mb-1 flex items-baseline gap-3">
        <h1 className="text-foreground font-serif text-2xl">Call Analytics</h1>
        <span className="text-muted-foreground font-mono text-[11px] tracking-[0.18em] uppercase">
          Day 8 · Performance
        </span>
      </div>
      <p className="text-muted-foreground mb-6 flex flex-wrap items-center gap-x-2 text-sm">
        How Dhan Saathi is performing, from real browser and phone calls.
        {stats && stats.active > 0 && (
          <span className="text-brass inline-flex items-center gap-1.5 font-medium">
            <span className="bg-brass inline-block size-1.5 animate-pulse rounded-full" />
            {stats.active} live now
          </span>
        )}
      </p>

      {error && (
        <div className="border-destructive/40 bg-destructive/10 text-destructive rounded-lg border px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {!error && !stats && <p className="text-muted-foreground text-sm">Reading the ledger…</p>}

      {!error && stats && (
        <>
          {/* Three ledger figures — the passbook balance */}
          <div className="mb-4 flex flex-col gap-4 sm:flex-row">
            <StatCard
              label="Total calls"
              value={stats.total}
              accent="border-t-2 border-t-foreground/60"
              sub="browser + phone, ended"
            />
            <StatCard
              label="Successful"
              value={stats.successful}
              accent="border-t-2 border-t-brass"
              sub="reached the goal"
            />
            <StatCard
              label="Failed"
              value={stats.failed}
              accent="border-t-2 border-t-destructive"
              sub="didn’t reach the goal"
            />
          </div>

          {/* Success-rate "balance" bar — the signature moment */}
          <div className="bg-card border-border/70 mb-6 rounded-xl border p-5 md:p-6">
            <div className="mb-2 flex items-baseline justify-between">
              <span className="text-muted-foreground font-mono text-[10px] font-medium tracking-[0.2em] uppercase">
                Success rate
              </span>
              <span className="text-foreground font-mono text-2xl font-bold tabular-nums">
                {stats.success_rate}%
              </span>
            </div>
            <div className="bg-muted h-2.5 overflow-hidden rounded-full">
              <div
                className="from-brass-soft to-brass h-full rounded-full bg-gradient-to-r transition-[width] duration-1000 ease-out"
                style={{ width: `${barWidth}%` }}
              />
            </div>
            <p className="text-muted-foreground mt-3 text-xs">
              A call counts as successful when the caller completes a scheme eligibility check, or a
              human-help request is raised.
            </p>
          </div>

          {/* Breakdowns */}
          <div className="mb-6 flex flex-col gap-4 md:flex-row">
            <MiniList
              title="By channel"
              entries={Object.fromEntries(
                Object.entries(stats.by_channel).map(([k, v]) => [k, v.total])
              )}
              labels={CHANNEL_LABEL}
              barClass="bg-foreground/60"
            />
            <MiniList
              title="Successes"
              entries={stats.by_success}
              labels={SUCCESS_LABEL}
              barClass="bg-brass"
            />
            <MiniList
              title="Failure types"
              entries={stats.by_failure}
              labels={FAILURE_LABEL}
              barClass="bg-destructive"
            />
          </div>

          {/* Recent calls — passbook entries */}
          <div className="bg-card border-border/70 overflow-hidden rounded-xl border">
            <div className="border-border/70 flex items-baseline justify-between border-b px-5 py-3.5">
              <h3 className="text-foreground font-serif text-base">Recent calls</h3>
              <span className="text-muted-foreground font-mono text-[10px] tracking-[0.18em] uppercase">
                newest first
              </span>
            </div>
            {calls.length === 0 ? (
              <p className="text-muted-foreground px-5 py-8 text-sm">
                No calls recorded yet. Make a browser or phone call to the agent and it will appear
                here.
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground font-mono text-[10px] tracking-[0.14em] uppercase">
                    <th className="px-5 py-2 text-left font-medium">Started</th>
                    <th className="py-2 text-left font-medium">Channel</th>
                    <th className="py-2 text-left font-medium">Duration</th>
                    <th className="py-2 text-left font-medium">Outcome</th>
                    <th className="py-2 pr-5 text-left font-medium">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.map((c) => {
                    const reason =
                      c.outcome === 'success'
                        ? (SUCCESS_LABEL[c.success_reason] ?? c.success_reason)
                        : c.outcome === 'failed'
                          ? (FAILURE_LABEL[c.failure_reason] ?? c.failure_reason)
                          : '—';
                    return (
                      <tr key={c.call_id} className="border-border/50 border-t">
                        <td className="text-foreground px-5 py-2.5 whitespace-nowrap">
                          <span className="font-mono tabular-nums">{fmtTime(c.started_at)}</span>
                          <span className="text-muted-foreground ml-2 font-mono text-[11px]">
                            {fmtDate(c.started_at)}
                          </span>
                        </td>
                        <td className="text-foreground/90 py-2.5">
                          {CHANNEL_LABEL[c.channel] ?? c.channel}
                        </td>
                        <td className="text-foreground/90 py-2.5 font-mono tabular-nums">
                          {fmtDuration(c.duration_seconds)}
                        </td>
                        <td className="py-2.5">
                          <OutcomePill outcome={c.outcome} />
                        </td>
                        <td className="text-muted-foreground py-2.5 pr-5">{reason}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          <p className="text-muted-foreground/70 mt-4 text-xs">
            Live from real calls · updates every 3s · no caller names, numbers, or transcripts are
            stored or shown.
          </p>
        </>
      )}
    </main>
  );
}
