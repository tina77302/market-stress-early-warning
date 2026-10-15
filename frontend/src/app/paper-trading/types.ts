export type Market = 'us' | 'korea';
export interface User { id: number; email: string | null; username?: string | null; role: 'user' | 'admin' }
export interface Security { market: Market; symbol: string; ticker: string; name: string; exchange: string; security_type: 'Stock' | 'ETF'; currency: string }
export interface Quote { id: string; market: Market; symbol: string; price: number; currency: string; observed_at: string; source: string; expires_at: number }
export interface Position { symbol: string; market: Market; quantity: number; average_cost: number; cost_basis: number; latest_price: number | null; market_value: number | null; unrealized_pnl: number | null; return_pct: number | null; price_observed_at: string | null }
export interface Portfolio { market: Market; currency: string; starting_cash: number; cash: number; portfolio_value: number | null; realized_pnl: number; unrealized_pnl: number | null; total_return_pct: number | null; today_pnl: number | null; today_pnl_note: string; valuation_complete: boolean; positions: Position[] }
export interface PaperOrder { execution_details?:ExecutionDetails|null; id: number; market: Market; symbol: string; side: 'BUY' | 'SELL'; quantity: number; execution_price: number; realized_pnl: number; executed_at: string; price_observed_at: string }
export interface PerformancePoint { observed_at: string; value: number; cash: number }
export interface OrderRequest { market: Market; symbol: string; side: 'BUY' | 'SELL'; quantity: number; quote_id: string; request_key: string; settlement_id?:string; fx_usd_cents?:number; fx_krw?:number }
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

// Keep persisted execution keys intact; provider suffixes are not display tickers.
export function displaySymbol(market: Market, symbol: string) {
  return market === 'korea' ? symbol.replace(/\.(KS|KQ)$/i, '') : symbol;
}

export interface PortfolioBook { portfolio: Portfolio; orders: PaperOrder[]; performance: PerformancePoint[] }
export type PortfolioBooks = Partial<Record<Market, PortfolioBook>>;
export interface FxObservation { freshness_status?:string; feed_delay_seconds?:number|null; max_observation_age_seconds?:number; max_retrieval_age_seconds?:number; rate_exact?:string; observation_timestamp?:string|null; selection_role?:string; fallback_reason?:string; id: string; rate: number; source: string; observation_date: string; retrieved_at: string; status: string }
export interface SettlementPlan { estimated_total_usd?:number|null; actual_usd_conversion_debit?:number; settlement_id?:string; currency?:string; costs?:TradeCosts; remaining_cash?:{USD:number;KRW:number}; total_cash_effect?:number; effective_fx_rate?:string|null; fx_spread_bps?:string; fx_cost_usd_exact?:string; base_order_value_usd?:number|null; quote_id: string; market: Market; symbol: string; side: 'BUY'|'SELL'; quantity: number; native_order_value: number; fx_usd_cents: number; fx_krw: number; from_currency: string|null; to_currency: string|null; fx: FxObservation|null }
export interface Investment { fx_attribution?:FxAttribution; cost_ledger?:Array<SettlementPlan & {order_id:number}>; realized_pnl_usd_translated?:number|null; unrealized_pnl_usd_translated?:number|null; cumulative_fees?:{USD:number;KRW:number}; cumulative_fees_usd_translated?:number|null; fx_conversion_costs_usd?:number; fx_conversions?:FxEvent[]; base_currency:'USD'; initial_capital:number; portfolio_value:number|null; cash:number|null; invested_value:number|null; total_pnl:number|null; total_return_pct:number|null; valuation_complete:boolean; observed_at:string; cash_balances:{USD:number;KRW:number}; fx:FxObservation|null; fx_error:string|null; books:Record<Market,Portfolio>; performance:PerformancePoint[] }

export interface FxEvent { order_id:number; from_currency:string; from_minor:number; to_currency:string; to_minor:number; usd_cash_after:number; krw_cash_after:number; quantity_after:number; symbol:string; market:Market; execution_price:number; effective_rate?:string|null; spread_bps?:string|null; fx_cost_usd?:string|null; rate:string; observation_date:string; executed_at:string; source:string }

export interface TradeCosts { gross_minor:number; commission_minor:number; transaction_tax_minor:number; regulatory_fee_minor:number; total_fees_minor:number; net_minor:number; trade_date:string; policy_version:string; policy_hash:string; security_type:string; exchange:string; components:Array<{name:string;category:string;minor:number;rate:string}>; unmodeled:string }

export interface FxPositionDetail { market:Market; symbol:string; quantity:number; average_purchase_price:number; average_acquisition_fx:number|null; current_fx:number|null; fx_change_pct:number|null; native_stock_pnl:number; native_effect_usd:number; fx_effect_usd:number; purchase_costs_usd:number; total_usd_pnl:number }
export interface FxAttribution { available:boolean; native_investment_effect_usd?:number; fx_translation_effect_usd?:number; trading_costs_usd?:number; fx_conversion_costs_usd?:number; krw_cash_fx_unrealized_usd?:number; reconciled_total_usd_pnl?:number; rounding_residual_usd?:number; krw_exposure_usd?:number; krw_exposure_pct?:number; positions:FxPositionDetail[] }
export interface ExecutionDetails extends SettlementPlan { execution_attribution?: {available:boolean; gross_usd?:string; fees_usd?:string; purchase_fx_basis?:string|null; native_realized_stock_pnl?:string; native_effect_usd?:string; fx_effect_usd?:string; net_realized_usd?:string; execution_fx?:FxObservation|null} }
