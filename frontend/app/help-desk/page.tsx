'use client';

import { useCallback, useEffect, useState } from 'react';

type Escalation = {
  ref_id: string;
  created_at: string;
  caller_name: string;
  reason_label: string;
  summary: string;
  checked: string;
  urgency: 'low' | 'medium' | 'high' | 'emergency';
  language: string;
  follow_up: string;
  status: 'open' | 'in_progress' | 'resolved';
  webhook_sent: number;
};

const TABS = ['open', 'in_progress', 'resolved', 'all'] as const;
type Tab = (typeof TABS)[number];

const URGENCY_COLOR: Record<string, string> = {
  emergency: 'bg-[#b00020]',
  high: 'bg-[#d35400]',
  medium: 'bg-[#b8860b]',
  low: 'bg-[#2e7d32]',
};
const STATUS_COLOR: Record<string, string> = {
  open: 'bg-[#d35400]',
  in_progress: 'bg-[#1565c0]',
  resolved: 'bg-[#2e7d32]',
};

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span
      className={`${color} rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide text-white uppercase`}
    >
      {text}
    </span>
  );
}

export default function HelpDeskPage() {
  const [tab, setTab] = useState<Tab>('open');
  const [items, setItems] = useState<Escalation[]>([]);
  const [openTotal, setOpenTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (which: Tab) => {
    try {
      const res = await fetch(`/api/escalations?status=${which}`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setItems(data.escalations ?? []);
      setOpenTotal(data.openCount ?? 0);
      setError(null);
    } catch {
      setError('Could not reach the escalation store. Is the backend DB present?');
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll every 3s so a request the agent raises appears without a manual refresh.
  useEffect(() => {
    load(tab);
    const id = setInterval(() => load(tab), 3000);
    return () => clearInterval(id);
  }, [tab, load]);

  async function setStatus(ref_id: string, status: string) {
    await fetch('/api/escalations', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ref_id, status }),
    });
    load(tab);
  }

  return (
    <main className="mx-auto max-w-3xl px-5 pt-24 pb-16 md:px-8">
      <div className="mb-1 flex items-baseline gap-3">
        <h1 className="text-foreground font-serif text-2xl">Human Help Desk</h1>
        <span className="text-muted-foreground font-mono text-[11px] tracking-[0.18em] uppercase">
          Day 7 · Escalations
        </span>
      </div>
      <p className="text-muted-foreground mb-5 text-sm">
        Requests the voice agent raised when it needed a real person.{' '}
        <span className="text-foreground font-medium">{openTotal}</span> open. Updates live.
      </p>

      <div className="mb-4 flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={
              t === tab
                ? 'bg-foreground text-background rounded-lg px-3.5 py-1.5 text-sm font-semibold'
                : 'border-border text-muted-foreground hover:text-foreground rounded-lg border px-3.5 py-1.5 text-sm'
            }
          >
            {t.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-lg border border-[#b00020]/40 bg-[#b00020]/10 px-4 py-3 text-sm text-[#ff8a8a]">
          {error}
        </div>
      )}

      {!error && loading && <p className="text-muted-foreground text-sm">Loading…</p>}

      {!error && !loading && items.length === 0 && (
        <p className="text-muted-foreground mt-8 text-sm">
          No requests in this view. A normal conversation should leave this empty.
        </p>
      )}

      <div className="space-y-3">
        {items.map((e) => (
          <article
            key={e.ref_id}
            className="border-border/70 bg-background/40 rounded-xl border p-4 md:p-5"
          >
            <div className="mb-3 flex flex-wrap items-center gap-2.5">
              <span className="text-foreground font-mono text-sm font-bold">{e.ref_id}</span>
              <Badge text={e.urgency} color={URGENCY_COLOR[e.urgency] ?? 'bg-gray-500'} />
              <Badge
                text={e.status.replace('_', ' ')}
                color={STATUS_COLOR[e.status] ?? 'bg-gray-500'}
              />
              <span className="flex-1" />
              <div className="flex gap-2 text-sm">
                {e.status !== 'in_progress' && (
                  <button
                    onClick={() => setStatus(e.ref_id, 'in_progress')}
                    className="text-[#5aa2e5] hover:underline"
                  >
                    Start
                  </button>
                )}
                {e.status !== 'resolved' && (
                  <button
                    onClick={() => setStatus(e.ref_id, 'resolved')}
                    className="text-[#5fbf6a] hover:underline"
                  >
                    Resolve
                  </button>
                )}
                {e.status !== 'open' && (
                  <button
                    onClick={() => setStatus(e.ref_id, 'open')}
                    className="text-muted-foreground hover:text-foreground hover:underline"
                  >
                    Reopen
                  </button>
                )}
              </div>
            </div>

            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <Row label="Reason" value={e.reason_label} />
              <Row label="Who" value={e.caller_name || 'unknown'} />
              <Row label="What happened" value={e.summary} />
              {e.checked && <Row label="Agent already checked" value={e.checked} />}
              {e.language && <Row label="Language" value={e.language} />}
              {e.follow_up && <Row label="Preferred follow-up" value={e.follow_up} />}
              <Row label="Created" value={e.created_at} />
              {e.webhook_sent ? <Row label="Forwarded to team channel" value="yes" /> : null}
            </dl>
          </article>
        ))}
      </div>
    </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-muted-foreground whitespace-nowrap">{label}</dt>
      <dd className="text-foreground">{value}</dd>
    </>
  );
}
