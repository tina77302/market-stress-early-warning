'use client';

import { LocalizedText, useI18n } from '../i18n/provider';

import SecurityPicker from './SecurityPicker';
import CurrentMarketRisk from './MarketRiskPanel';

import { FormEvent, useEffect, useState } from 'react';
import { Market, OrderRequest, Portfolio, Quote, Security, value as formatValue, workspace, displaySymbol } from './types';

export default function TradeTicket({ market, portfolio, csrf, userId, onExecuted }: { market: Market; portfolio: Portfolio | null; csrf: string; userId: number; onExecuted: () => void }) {
  const { t, locale } = useI18n();
  const value = (number: unknown, currency?: string) => formatValue(number, currency, locale);

  const [selection, setSelection] = useState<Security | null>(null);
  const [symbol, setSymbol] = useState('');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [quantity, setQuantity] = useState('1');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [review, setReview] = useState<OrderRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState('');
  const pendingKey = `mri-pending-order:${userId}:${market}`;
  useEffect(() => {
    // An uncertain network outcome can be retried with the exact same idempotency key after reload.
    const saved = sessionStorage.getItem(pendingKey);
    if (saved) { try { const order: OrderRequest = JSON.parse(saved); setReview(order); setSymbol(order.symbol); setSide(order.side); setQuantity(String(order.quantity)); setError('An earlier submission has an uncertain outcome. Retry the saved request safely or refresh order history.'); } catch { sessionStorage.removeItem(pendingKey); } }
  }, [market, pendingKey]);
  function change() { setReview(null); setQuote(null); setError(''); setResult(''); }
  async function loadQuote(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setReview(null); setQuote(null); setResult('');
    try { setQuote(await workspace<Quote>(`paper/quote?market=${market}&symbol=${encodeURIComponent(symbol)}`)); }
    catch (error) { setError(error instanceof Error ? error.message : 'Price unavailable.'); }
    finally { setBusy(false); }
  }
  const units = Number(quantity);
  const validQuantity = /^\d+$/.test(quantity) && Number.isSafeInteger(units) && units > 0 && units <= 1000000;
  const availableShares = portfolio?.positions.find(position => position.symbol === symbol)?.quantity || 0;
  const total = quote && validQuantity ? quote.price * units : null;
  const affordable = portfolio && total !== null && (side === 'BUY' ? total <= portfolio.cash : units <= availableShares);
  function prepare() {
    if (!quote || !validQuantity || !affordable) return;
    if (quote.expires_at * 1000 <= Date.now()) { setError('Quote expired. Load a new price before reviewing.'); return; }
    setReview({ market, symbol, side, quantity: units, quote_id: quote.id, request_key: crypto.randomUUID() });
  }
  async function execute() {
    if (!review) return;
    setBusy(true); setError(''); setResult('');
    sessionStorage.setItem(pendingKey, JSON.stringify(review));
    try { await workspace('paper/orders', { body: review, csrf }); sessionStorage.removeItem(pendingKey); setReview(null); setQuote(null); setResult('Simulated order filled. Portfolio and order history are refreshing.'); onExecuted(); }
    catch (error) { setError(error instanceof Error ? error.message : 'Order outcome uncertain. Retry this same request safely.'); }
    finally { setBusy(false); }
  }
  return <aside className="history-panel trade-ticket"><div className="rw-section-heading"><div><div className="eyebrow"><LocalizedText id="rw_simulated_order"/></div><h2><LocalizedText id="command_search_trade"/></h2></div><span className="rw-tag"><LocalizedText id="rw_no_real_money"/></span></div><p className="comparison-note"><LocalizedText>{market === 'us' ? 'U.S. · USD' : 'Korea · KRW'}</LocalizedText><LocalizedText id="simulated_whole_share_orders_1626bc" before/></p><SecurityPicker key={market} market={market} disabled={busy || !!review} onSearchStart={()=>{change();setSelection(null);setSymbol('');}} onSelect={item=>{change();setSelection(item);setSymbol(item.symbol);}}/>
    {symbol && <div className="security-selected"><strong>{selection?.ticker || displaySymbol(market,symbol)}</strong>{selection && <><span>{selection.name}</span><small>{selection.exchange} · <LocalizedText>{market==='us'?'U.S.':'Korea'}</LocalizedText> · <LocalizedText id={selection.security_type==='ETF'?'security_type_etf':'security_type_stock'}/></small></>}<small><LocalizedText id="security_selection_note"/></small></div>}
    <form onSubmit={loadQuote}><button className="paper-secondary" disabled={!symbol || busy || !!review}><LocalizedText>{busy ? 'Loading…' : 'Load latest completed close'}</LocalizedText></button></form>
    {quote && <div className="ticket-price"><strong><LocalizedText>{value(quote.price, quote.currency)}</LocalizedText></strong><span><LocalizedText>{quote.source}</LocalizedText></span><small><LocalizedText id="price_observed_1c7d19" after/><LocalizedText>{new Date(quote.observed_at).toLocaleString(locale)}</LocalizedText><LocalizedText id="quote_valid_for_two_minutes_cb7b71" before/></small></div>}
    <div className="paper-segment"><button disabled={busy || !!review} aria-pressed={side === 'BUY'} onClick={() => {setSide('BUY');setReview(null);}}><LocalizedText id="buy_7ceca5"/></button><button disabled={busy || !!review} aria-pressed={side === 'SELL'} onClick={() => {setSide('SELL');setReview(null);}}><LocalizedText id="sell_fa3cf2"/></button></div><label><LocalizedText id="whole_share_quantity_0a8e2b"/><input type="number" min="1" step="1" max="1000000" value={quantity} disabled={busy || !!review} onChange={event => {setQuantity(event.target.value);setReview(null);}}/></label><dl className="ticket-estimate"><div><dt><LocalizedText id="estimated_order_value_e84916"/></dt><dd><LocalizedText>{value(total, portfolio?.currency)}</LocalizedText></dd></div><div><dt><LocalizedText id="available_cash_80c2a4"/></dt><dd><LocalizedText>{value(portfolio?.cash, portfolio?.currency)}</LocalizedText></dd></div><div><dt><LocalizedText id="available_shares_217808"/></dt><dd><LocalizedText>{availableShares}</LocalizedText></dd></div></dl>
    <div className="command-order-context"><div className="eyebrow"><LocalizedText id="command_market_context"/></div><CurrentMarketRisk market={market}/></div>
    {!review && <button className="paper-primary" disabled={busy || !quote || !affordable || !validQuantity || !csrf} onClick={prepare}><LocalizedText id="review_simulated_order_fd4ef9"/></button>}
    {review && <section className="order-review" aria-label={t("Simulated order review")}><h3><LocalizedText id="confirm_paper_trade_9bd574"/></h3><p><LocalizedText>{`${review.side} ${review.quantity} shares of ${displaySymbol(market,review.symbol)}.`}</LocalizedText></p><p><LocalizedText>{quote ? `At ${value(quote.price, quote.currency)} per share · ${value(total, quote.currency)} total.` : 'Retrying a previously saved request; the original server quote and order details will be verified.'}</LocalizedText></p><p><LocalizedText id="simulated_fill_at_a_completed_daily_close_cash_and_shares_will_up_d1b0a9"/></p><button className="paper-primary" disabled={busy || !csrf} onClick={execute}><LocalizedText>{busy ? 'Submitting…' : 'Submit paper trade'}</LocalizedText></button><button className="paper-secondary" disabled={busy} onClick={() => {sessionStorage.removeItem(pendingKey);change();}}><LocalizedText id="cancel_review_334c92"/></button></section>}
    <LocalizedText>{error && <p className="paper-error" role="alert"><LocalizedText>{error}</LocalizedText></p>}<LocalizedText></LocalizedText>{result && <p role="status"><LocalizedText>{result}</LocalizedText></p>}</LocalizedText>
  </aside>;
}
