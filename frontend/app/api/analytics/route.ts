import { NextResponse } from 'next/server';
import { getStats, recentCalls } from '@/lib/analytics';

// node-sqlite3-wasm needs the Node runtime (not Edge), and the data changes on
// every call, so never cache.
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

// GET /api/analytics
// Returns the Day 8 call analytics: total/successful/failed and a recent history.
export async function GET() {
  try {
    return NextResponse.json(
      { stats: getStats(), calls: recentCalls(25) },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  } catch (error) {
    console.error('Failed to read call analytics', error);
    return NextResponse.json({ error: 'Could not read call analytics' }, { status: 500 });
  }
}
