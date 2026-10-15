'use client';

import { LocalizedText, useI18n } from '../i18n/provider';

import SecurityPicker from './SecurityPicker';
import CurrentMarketRisk from './MarketRiskPanel';
import { FxAttribution, isExchangeRate } from './FxDisclosure';
import { estimatedOrder, quoteFailure, selectedQuote, settlementPortfolio } from './workflow';

import { FormEvent, useEffect, useState, useRef } from 'react';
import { Market, OrderRequest, Portfolio, Quote, SettlementPlan, Security, value as formatValue, workspace, displaySymbol } from './types';

export default function TradeTicket({ market: initialMarket = 'us', portfolio: fallback, portfolios, csrf, userId, onExecuted }: { market?: Market; portfolio?: Portfolio | null; portfolios?: Partial<Record<Market, Portfolio | null>>; csrf: string; userId: number; onExecuted: () => void }) {
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
  const [market, setMarket] = useState<Market>(initialMarket);
  const [plan,setPlan]=useState<SettlementPlan|null>(null);
  const [planError,setPlanError]=useState('');
  const quoteRequest = useRef<AbortController | null>(null);
  const portfolio = settlementPortfolio(market,portfolios,fallback);
  useEffect(()=>()=>quoteRequest.current?.abort(),[userId]);
  useEffect(()=>{
    // Restore an uncertain request from either currency book after reloading the unified UI.
    for(const book of ['us','korea'] as const) if(sessionStorage.getItem(`mri-pending-order:${userId}:${book}`)) {setMarket(book);break;}
  },[userId]);
  const pendingKey = `mri-pending-order:${userId}:${market}`;
  useEffect(() => {
    // An uncertain network outcome can be retried with the exact same idempotency key after reload.
    const saved = sessionStorage.getItem(pendingKey);
    if (saved) { try { const order: OrderRequest = JSON.parse(saved); quoteRequest.current?.abort(); setBusy(false); setQuote(null); setSelection(null); setReview(order); setSymbol(order.symbol); setSide(order.side); setQuantity(String(order.quantity)); setError('An earlier submission has an uncertain outcome. Retry the saved request safely or refresh order history.'); } catch { sessionStorage.removeItem(pendingKey); } }
  }, [market, pendingKey]);
  function change() { quoteRequest.current?.abort(); setBusy(false); setReview(null); setQuote(null); setError(''); setResult(''); }
  async function requestQuote(item: Pick<Security,'market'|'symbol'|'currency'>) {
    quoteRequest.current?.abort();
    const controller = new AbortController();quoteRequest.current=controller;
    setBusy(true);setError('');setReview(null);setQuote(null);setResult('');
    try { const loaded = await selectedQuote(item,controller.signal); if(!controller.signal.aborted)setQuote(loaded); }
    catch(error) { if(!controller.signal.aborted)setError(quoteFailure(error)); }
    finally { if(!controller.signal.aborted)setBusy(false); }
  }
  function loadQuote(event: FormEvent) {
    event.preventDefault();
    void requestQuote({market,symbol,currency:market==='us'?'USD':'KRW'});
  }
  function selectSecurity(item: Security) {
    change();setSelection(item);setSymbol(item.symbol);setMarket(item.market);
    void requestQuote(item);
  }
  const units = Number(quantity);
  const validQuantity = /^\d+$/.test(quantity) && Number.isSafeInteger(units) && units > 0 && units <= 1000000;
  const availableShares = portfolio?.positions.find(position => position.symbol === symbol)?.quantity || 0;
  const total = estimatedOrder(quote,quantity);
  useEffect(()=>{
    // Keep the reviewed immutable preview visible through final confirmation.
    if(review)return;
    const controller=new AbortController();setPlan(null);setPlanError('');
    if(!quote || !validQuantity || review)return ()=>controller.abort();
    const timer=setTimeout(()=>{void workspace<SettlementPlan>(`paper/settlement?quote_id=${quote.id}&side=${side}&quantity=${units}`,{signal:controller.signal}).then(result=>{if(!controller.signal.aborted)setPlan(result);}).catch(error=>{if(!controller.signal.aborted)setPlanError(error instanceof Error?error.message:'Settlement unavailable.');});},200);
    return ()=>{clearTimeout(timer);controller.abort();};
  },[quote,side,units,validQuantity,review]);
  const planMatches=!!plan?.settlement_id && !!plan?.costs && plan?.quote_id===quote?.id && plan?.market===market && plan?.symbol===symbol && plan?.quantity===units && plan?.side===side;
  const affordable = portfolio && planMatches && (side==='BUY' || units<=availableShares);
  function prepare() {
    if (!quote || !validQuantity || !affordable || quote.market!==market || quote.symbol!==symbol || quote.currency!==portfolio?.currency) return;
    if (quote.expires_at * 1000 <= Date.now()) { setError('Quote expired. Load a new price before reviewing.'); return; }
    setReview({ market, symbol, side, quantity: units, quote_id: quote.id, request_key: crypto.randomUUID(), settlement_id:plan?.settlement_id, fx_usd_cents:plan?.fx_usd_cents ?? 0,fx_krw:plan?.fx_krw ?? 0 });
  }
  async function execute() {
    if (!review) return;
    setBusy(true); setError(''); setResult('');
    sessionStorage.setItem(pendingKey, JSON.stringify(review));
    try { await workspace('paper/orders', { body: review, csrf }); sessionStorage.removeItem(pendingKey); setReview(null); setQuote(null); setResult('Simulated order filled. Portfolio and order history are refreshing.'); onExecuted(); }
    catch (error) { setError(error instanceof Error ? error.message : 'Order outcome uncertain. Retry this same request safely.'); }
    finally { setBusy(false); }
  }
  return <aside className="history-panel trade-ticket"><div className="rw-section-heading"><div><div className="eyebrow"><LocalizedText id="rw_simulated_order"/></div><h2><LocalizedText id="command_search_trade"/></h2></div><span className="rw-tag"><LocalizedText id="rw_no_real_money"/></span></div><p className="comparison-note"><LocalizedText id="unified_search_scope"/></p><p className="comparison-note"><LocalizedText>{market === 'us' ? 'U.S. · USD' : 'Korea · KRW'}</LocalizedText><LocalizedText id="simulated_whole_share_orders_1626bc" before/></p><SecurityPicker market="all" disabled={!!review} onSearchStart={()=>{change();setSelection(null);setSymbol('');}} onSelect={selectSecurity}/>
    {symbol && <div className="security-selected"><strong>{selection?.ticker || displaySymbol(market,symbol)}</strong>{selection && <><span>{selection.name}</span><small>{selection.exchange} · <LocalizedText>{market==='us'?'U.S.':'Korea'}</LocalizedText> · <LocalizedText id={selection.security_type==='ETF'?'security_type_etf':'security_type_stock'}/> · {selection.currency}</small></>}<small><LocalizedText id="security_selection_note"/></small></div>}
    <form onSubmit={loadQuote}><button className="paper-secondary" disabled={!symbol || busy || !!review}><LocalizedText>{busy ? 'Loading…' : 'Refresh validated quote'}</LocalizedText></button></form>
    {(selection || review) && <p className="unified-settlement"><LocalizedText id="capital_settlement_currency"/> <strong>{market==='us'?'USD':'KRW'}</strong> · <LocalizedText id="capital_simulated_fx"/></p>}
    {quote && <div className="ticket-price"><strong><LocalizedText>{value(quote.price, quote.currency)}</LocalizedText></strong><span><LocalizedText>{quote.source}</LocalizedText></span><small><LocalizedText id="price_observed_1c7d19" after/><LocalizedText>{new Date(quote.observed_at).toLocaleString(locale)}</LocalizedText><LocalizedText id="quote_valid_for_two_minutes_cb7b71" before/></small></div>}
    <div className="paper-segment"><button disabled={busy || !!review} aria-pressed={side === 'BUY'} onClick={() => {setSide('BUY');setReview(null);}}><LocalizedText id="buy_7ceca5"/></button><button disabled={busy || !!review} aria-pressed={side === 'SELL'} onClick={() => {setSide('SELL');setReview(null);}}><LocalizedText id="sell_fa3cf2"/></button></div><label><LocalizedText id="whole_share_quantity_0a8e2b"/><input type="number" min="1" step="1" max="1000000" value={quantity} disabled={busy || !!review} onChange={event => {setQuantity(event.target.value);setReview(null);}}/></label><dl className="ticket-estimate"><div><dt><LocalizedText id="estimated_order_value_e84916"/></dt><dd>{busy ? <LocalizedText id="unified_quote_loading"/> : !quote ? <LocalizedText id={error ? 'unified_quote_failed' : 'unified_select_security'}/> : <LocalizedText>{value(total, quote?.currency)}</LocalizedText>}</dd></div><div><dt><LocalizedText id="available_cash_80c2a4"/> · {market==='us'?'USD':'KRW'}</dt><dd><LocalizedText>{value(portfolio?.cash, portfolio?.currency)}</LocalizedText></dd></div><div><dt><LocalizedText id="available_shares_217808"/></dt><dd><LocalizedText>{availableShares}</LocalizedText></dd></div></dl>
    {planMatches && plan && <div className="capital-settlement"><p><LocalizedText id="capital_settlement_rule"/></p>{plan.base_order_value_usd!=null && <p><LocalizedText id="capital_usd_equivalent"/> ≈ {value(plan.base_order_value_usd,'USD')}</p>}{plan.fx && <p>{'USD/KRW'} {plan.fx.rate} · {plan.fx.source} · {plan.fx.observation_timestamp || plan.fx.observation_date}{plan.fx.retrieved_at && <> · <LocalizedText id="capital_fx_retrieved"/> {new Date(plan.fx.retrieved_at).toLocaleString(locale)}</>}</p>}{plan.fx && plan.from_currency && <><strong>{plan.from_currency} → {plan.to_currency}</strong><p>{'USD'} {value(plan.fx_usd_cents/100,'USD')} · {'KRW'} {value(plan.fx_krw,'KRW')}</p><p><LocalizedText id="capital_conversion_consent"/></p></>}{plan.costs && <dl className="ticket-estimate cost-preview">
      <div><dt><LocalizedText id="cost_gross"/></dt><dd>{value(plan.native_order_value,plan.currency)}</dd></div>
      <div><dt><LocalizedText id="cost_commission"/></dt><dd>{value(plan.costs.commission_minor/(market==='us'?100:1),plan.currency)}</dd></div>
      <div><dt><LocalizedText id="cost_transaction_tax"/></dt><dd>{value(plan.costs.transaction_tax_minor/(market==='us'?100:1),plan.currency)}</dd></div>
      <div><dt><LocalizedText id="cost_regulatory"/></dt><dd>{value(plan.costs.regulatory_fee_minor/(market==='us'?100:1),plan.currency)}</dd></div>
      {plan.costs.components.map(component=><div className="cost-component" key={component.name}><dt><LocalizedText id={component.name==='securities_transaction_tax'?'cost_stt':component.name==='agricultural_special_tax'?'cost_agricultural':component.name==='SEC_section_31'?'cost_sec':'cost_taf'}/></dt><dd>{value(component.minor/(market==='us'?100:1),plan.currency)}</dd></div>)}
      <div><dt><LocalizedText id={side==='BUY'?'cost_total_debit':'cost_net_proceeds'}/></dt><dd>{value(plan.total_cash_effect,plan.currency)}</dd></div>
      <div><dt><LocalizedText id="cost_fx_spread"/></dt><dd>{plan.from_currency?`${plan.fx_spread_bps} bps`:<LocalizedText id="cost_not_applied"/>}</dd></div>
      {plan.effective_fx_rate && <div><dt><LocalizedText id="cost_applied_fx"/></dt><dd>{plan.effective_fx_rate}</dd></div>}
      <div><dt><LocalizedText id="cost_fx_cost"/></dt><dd>{value(Number(plan.fx_cost_usd_exact ?? '0'),'USD')}</dd></div>
      <div><dt><LocalizedText id="fx_actual_usd_debit"/></dt><dd>{value(plan.actual_usd_conversion_debit,'USD')}</dd></div>
      <div><dt><LocalizedText id="fx_estimated_total_usd"/></dt><dd>{value(plan.estimated_total_usd,'USD')}</dd></div>
      <div><dt><LocalizedText id="cost_remaining_usd"/></dt><dd>{value(plan.remaining_cash?.USD,'USD')}</dd></div>
      <div><dt><LocalizedText id="cost_remaining_krw"/></dt><dd>{value(plan.remaining_cash?.KRW,'KRW')}</dd></div>
    </dl>}{plan.fx && <p><LocalizedText id="fx_execution_snapshot"/> · <LocalizedText id={isExchangeRate(plan.fx.source)?'fx_exchange_delayed':plan.fx.selection_role==='fallback'?'fx_daily_fallback':plan.fx.selection_role==='primary'?'fx_higher_frequency':'capital_fx_limits'}/></p>}<FxAttribution source={plan.fx?.source}/><small><LocalizedText id="cost_assumptions"/> · {plan.costs?.policy_version} · {plan.costs?.trade_date}</small><p><LocalizedText id="cost_exclusions"/></p><small><LocalizedText id="capital_rounding"/></small></div>}
    {planError && <p className="paper-error" role="alert"><LocalizedText>{planError}</LocalizedText></p>}
    <div className="command-order-context"><div className="eyebrow"><LocalizedText id="command_market_context"/></div>{symbol ? <CurrentMarketRisk market={market}/> : <p className="comparison-note"><LocalizedText id="unified_risk_select"/></p>}</div>
    {!review && <button className="paper-primary" disabled={busy || !quote || !affordable || !validQuantity || !csrf} onClick={prepare}><LocalizedText id="review_simulated_order_fd4ef9"/></button>}
    {review && <section className="order-review" aria-label={t("Simulated order review")}><h3><LocalizedText id="confirm_paper_trade_9bd574"/></h3><p><LocalizedText>{`${review.side} ${review.quantity} shares of ${displaySymbol(market,review.symbol)}.`}</LocalizedText></p><p><LocalizedText>{quote ? `At ${value(quote.price, quote.currency)} per share · ${value(total, quote.currency)} total.` : 'Retrying a previously saved request; the original server quote and order details will be verified.'}</LocalizedText></p><p><LocalizedText id="simulated_fill_at_a_completed_daily_close_cash_and_shares_will_up_d1b0a9"/></p>{planMatches && plan && <div className="review-settlement"><dl className="ticket-estimate review-costs">
      {plan.costs && <div><dt><LocalizedText id="cost_commission"/></dt><dd>{value(plan.costs.commission_minor/(market==='us'?100:1),plan.currency)}</dd></div>}
      <div><dt><LocalizedText id={side==='BUY'?'cost_total_debit':'cost_net_proceeds'}/></dt><dd>{value(plan.total_cash_effect,plan.currency)}</dd></div>
      <div><dt><LocalizedText id="cost_fx_cost"/></dt><dd>{value(Number(plan.fx_cost_usd_exact ?? '0'),'USD')}</dd></div>
      <div><dt><LocalizedText id="fx_estimated_total_usd"/></dt><dd>{value(plan.estimated_total_usd,'USD')}</dd></div>
    </dl>{plan.from_currency && <p>{plan.from_currency} → {plan.to_currency} · {value(plan.fx_usd_cents/100,'USD')} → {value(plan.fx_krw,'KRW')}</p>}{plan.fx && <p className="comparison-note">{plan.fx.source} · {plan.fx.observation_timestamp || plan.fx.observation_date}</p>}</div>}<button className="paper-primary" disabled={busy || !csrf} onClick={execute}><LocalizedText>{busy ? 'Submitting…' : 'Submit paper trade'}</LocalizedText></button><button className="paper-secondary" disabled={busy} onClick={() => {sessionStorage.removeItem(pendingKey);change();}}><LocalizedText id="cancel_review_334c92"/></button></section>}
    {error && <p className="paper-error" role="alert"><LocalizedText>{error}</LocalizedText></p>}{result && <p role="status"><LocalizedText>{result}</LocalizedText></p>}
  </aside>;
}
