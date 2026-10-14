import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
const allowed = new Set(['auth/register', 'auth/login', 'auth/logout', 'auth/me', 'admin/overview', 'admin/users', 'admin/data-health', 'paper/securities', 'paper/quote', 'paper/portfolio', 'paper/positions', 'paper/orders', 'paper/performance']);
async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const path = (await params).path.join('/');
  if (!allowed.has(path)) return NextResponse.json({ detail: 'Unknown workspace endpoint.' }, { status: 404 });
  if (request.method === 'POST') {
    const origin = request.headers.get('origin');
    let trusted = false;
    try { trusted = !!origin && new URL(origin).host === request.headers.get('host'); } catch { trusted = false; }
    if (!trusted) return NextResponse.json({ detail: 'Untrusted request origin.' }, { status: 403 });
    if (!request.headers.get('content-type')?.startsWith('application/json')) return NextResponse.json({ detail: 'JSON required.' }, { status: 415 });
  }
  const headers = new Headers({ 'content-type': 'application/json' });
  const cookie = request.cookies.get('mri_paper_session');
  if (cookie) headers.set('cookie', `mri_paper_session=${cookie.value}`);
  const csrf = request.headers.get('x-csrf-token');
  if (csrf) headers.set('x-csrf-token', csrf);
  const origin = request.headers.get('origin');
  if (origin) headers.set('origin', origin);
  try {
    const body = request.method === 'POST' ? await request.text() : undefined;
    if (body && body.length > 16384) return NextResponse.json({ detail: 'Request too large.' }, { status: 413 });
    const upstream = await fetch(`${process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000'}/api/${path}${request.nextUrl.search}`, { method: request.method, headers, body, cache: 'no-store', signal: AbortSignal.timeout(60000) });
    const response = new NextResponse(await upstream.text(), { status: upstream.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
    const session = upstream.headers.get('set-cookie');
    if (session) response.headers.set('set-cookie', session);
    return response;
  } catch {
    return NextResponse.json({ detail: 'Workspace service unavailable. Please retry.' }, { status: 503 });
  }
}
export const GET = proxy;
export const POST = proxy;
