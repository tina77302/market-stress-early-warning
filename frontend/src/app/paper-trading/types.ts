export type Market = 'us' | 'korea';
export interface User { id: number; email: string; role: 'user' | 'admin' }
export interface Security { market: Market; symbol: string; name: string; currency: string }
export interface Quote { id: string; market: Market; symbol: string; price: number; currency: string; observed_at: string; source: string; expires_at: number }
export interface Position { symbol: string; market: Market; quantity: number; average_cost: number; cost_basis: number; latest_price: number | null; market_value: number | null; unrealized_pnl: number | null; return_pct: number | null; price_observed_at: string | null }
export interface Portfolio { market: Market; currency: string; starting_cash: number; cash: number; portfolio_value: number | null; realized_pnl: number; unrealized_pnl: number | null; total_return_pct: number | null; today_pnl: number | null; today_pnl_note: string; valuation_complete: boolean; positions: Position[] }
export interface PaperOrder { id: number; market: Market; symbol: string; side: 'BUY' | 'SELL'; quantity: number; execution_price: number; realized_pnl: number; executed_at: string; price_observed_at: string }
export interface PerformancePoint { observed_at: string; value: number; cash: number }
export interface OrderRequest { market: Market; symbol: string; side: 'BUY' | 'SELL'; quantity: number; quote_id: string; request_key: string }
export class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
export async function workspace<T>(path: string, options: { body?: unknown; csrf?: string; signal?: AbortSignal } = {}): Promise<T> {
  const response = await fetch(`/api/workspace/${path}`, { method: options.body === undefined ? 'GET' : 'POST', headers: { 'content-type': 'application/json', ...(options.csrf ? { 'x-csrf-token': options.csrf } : {}) }, body: options.body === undefined ? undefined : JSON.stringify(options.body), cache: 'no-store', signal: options.signal });
  const result = await response.json();
  if (!response.ok) throw new ApiError(typeof result.detail === 'string' ? result.detail : Array.isArray(result.detail) ? result.detail.map((item: { msg?: string }) => item.msg || 'Invalid request').join('; ') : 'Workspace request failed.', response.status);
  return result as T;
}
export function value(number: unknown, currency?: string, locale = 'en-US'): string {
  if (typeof number !== 'number' || !Number.isFinite(number)) return 'Unavailable';
  return currency ? new Intl.NumberFormat(locale, { style: 'currency', currency, currencyDisplay: 'narrowSymbol', maximumFractionDigits: currency === 'KRW' ? 0 : 2 }).format(number) : new Intl.NumberFormat(locale, {minimumFractionDigits:2,maximumFractionDigits:2}).format(number);
}
