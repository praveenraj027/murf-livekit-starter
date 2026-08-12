import { NextResponse } from 'next/server';
import { listEscalations, openCount, updateStatus } from '@/lib/escalations';

// node-sqlite3-wasm needs the Node runtime (not Edge), and the data changes on
// every call, so never cache.
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

// GET /api/escalations?status=open|in_progress|resolved|all
// Returns the requests for the human help desk plus the count still open.
export async function GET(req: Request) {
  try {
    const status = new URL(req.url).searchParams.get('status') ?? undefined;
    const escalations = listEscalations(status);
    return NextResponse.json(
      { escalations, openCount: openCount() },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  } catch (error) {
    console.error('Failed to read escalations', error);
    return NextResponse.json({ error: 'Could not read escalations' }, { status: 500 });
  }
}

// PATCH /api/escalations  { ref_id, status }
// The human moves a request open -> in_progress -> resolved.
export async function PATCH(req: Request) {
  try {
    const body = await req.json().catch(() => ({}));
    const refId = String(body?.ref_id ?? '');
    const status = String(body?.status ?? '');
    if (!refId || !status) {
      return NextResponse.json({ error: 'ref_id and status are required' }, { status: 400 });
    }
    const updated = updateStatus(refId, status);
    if (!updated) {
      return NextResponse.json({ error: 'Unknown ref_id or status' }, { status: 404 });
    }
    return NextResponse.json({ escalation: updated }, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    console.error('Failed to update escalation', error);
    return NextResponse.json({ error: 'Could not update escalation' }, { status: 500 });
  }
}
