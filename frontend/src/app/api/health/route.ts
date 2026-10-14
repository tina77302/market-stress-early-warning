export function GET() {
  return Response.json({ status: 'ok', service: 'frontend' }, { headers: { 'cache-control': 'no-store' } });
}
