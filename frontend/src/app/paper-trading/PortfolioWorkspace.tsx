'use client';

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { LocalizedText, useI18n } from '../i18n/provider';
import { finite } from '../components/market-data';
import TradeTicket from './TradeTicket';
import StressAnalytics from './StressAnalytics';
import { FxAttribution, FxDelay, isExchangeRate } from './FxDisclosure';
import { ExecutionDetails, FxEvent, Investment, Market, PaperOrder, PerformancePoint, Portfolio, PortfolioBooks, User, value as formatValue, displaySymbol } from './types';

const pnlClass = (number: number | null | undefined) => !finite(number) || number === 0 ? '' : number > 0 ? 'paper-gain' : 'paper-loss';

export function PortfolioPerformance({ performance, portfolio, currency, loading }: { performance: PerformancePoint[]; portfolio: Portfolio | null; currency: string; loading: boolean }) {
  const { t, locale } = useI18n();
  const value = (amount: unknown) => formatValue(amount, currency, locale);
  const invested = finite(portfolio?.portfolio_value) ? portfolio.portfolio_value - portfolio.cash : null;
  const share = portfolio?.portfolio_value && invested !== null ? Math.max(0, Math.min(100, invested / portfolio.portfolio_value * 100)) : null;
  const observations = performance.filter(point => finite(point.value) && Number.isFinite(Date.parse(point.observed_at)));
  const distinctTimes = new Set(observations.map(point => Date.parse(point.observed_at))).size;
  const distinctValues = new Set(observations.map(point => point.value)).size;
  const distinctDates = new Set(observations.map(point => new Date(point.observed_at).toISOString().slice(0,10))).size;
  const chartReady = distinctTimes >= 2 && distinctDates >= 2 && distinctValues >= 2;
  const historyState = !observations.length ? 'second_history_empty' : distinctTimes < 2 || distinctDates < 2 ? 'second_history_insufficient' : 'second_history_unchanged';
  return <section className="history-panel rw-performance" data-history-state={chartReady ? 'chart' : historyState}>
    <div className="rw-section-heading"><div><div className="eyebrow"><LocalizedText id="rw_account_history"/></div><h2><LocalizedText id="portfolio_performance_26ee77"/></h2></div><span className="rw-tag">{currency}</span></div>
    <div className="rw-chart-legend"><span><i aria-hidden="true"/><LocalizedText id="rw_total_equity"/></span><span><LocalizedText id="rw_recorded_only"/></span></div>
    <div className="history-chart">{!loading && chartReady ? <ResponsiveContainer width="100%" height="100%"><LineChart data={observations} margin={{ top: 12, right: 12, bottom: 10, left: 0 }}>
      <CartesianGrid stroke="#252e38" vertical={false}/><XAxis dataKey="observed_at" tickFormatter={date => new Date(date).toLocaleDateString(locale, { month: 'short', day: 'numeric' })} minTickGap={65} tick={{ fill: '#8d9ba8', fontSize: 12 }} axisLine={false} tickLine={false}/>
      <YAxis domain={['auto','auto']} width={70} tickFormatter={number => new Intl.NumberFormat(locale, { notation: 'compact' }).format(number)} tick={{ fill: '#8d9ba8', fontSize: 12 }} axisLine={false} tickLine={false}/>
      <Tooltip labelFormatter={date => new Date(date).toLocaleString(locale)} formatter={(amount: number) => [value(amount), t('Total equity')]} contentStyle={{ background: '#151c24', border: '1px solid #35404c', borderRadius: 8, fontSize: 14 }}/>
      <Line type="linear" dataKey="value" stroke="#6ba9ef" strokeWidth={2} dot={performance.length < 20} activeDot={{ r: 4 }} isAnimationActive={false}/>
    </LineChart></ResponsiveContainer> : <div className="chart-empty command-history-state" role="status"><div className="command-history-glyph" aria-hidden="true">↗</div><h3><LocalizedText id={loading ? 'second_history_loading' : historyState}/></h3><p><LocalizedText id={loading ? 'second_history_loading_note' : 'second_history_note'}/></p>{!loading && observations.length > 0 && <div className="command-history-facts"><span><LocalizedText id="second_recorded_equity"/><strong>{value(observations[observations.length - 1].value)}</strong></span><span><LocalizedText id="second_distinct_observations"/><strong>{distinctTimes.toLocaleString(locale)}</strong></span></div>}<small><LocalizedText id="additional_visits_and_fills_record_actual_observations_no_histori_7c82f9"/></small></div>}</div>
    <div className="rw-performance-footer"><span><LocalizedText id="rw_history_limit"/></span>{observations.length > 0 && <span><LocalizedText id="rw_latest_record" after/>{new Date(observations[observations.length - 1].observed_at).toLocaleString(locale)}</span>}</div>
    {share !== null && <div className="paper-allocation"><div className="rw-allocation-labels"><span><LocalizedText id="rw_invested_value"/> {share.toFixed(1)}%</span><span><LocalizedText id="rw_available_cash"/> {(100 - share).toFixed(1)}%</span></div><div className="rw-allocation-track" aria-hidden="true"><i style={{ width: `${share}%` }}/></div></div>}
  </section>;
}

export function PositionsTable({ portfolio, currency, loading }: { portfolio: Portfolio | null; currency: string; loading: boolean }) {
  const { locale } = useI18n();
  const value = (amount: unknown) => formatValue(amount, currency, locale);
  const headings = ['rw_symbol','rw_market_value','rw_quantity','rw_avg_cost','rw_current_price','rw_unrealized','rw_return'] as const;
  return <section className="history-panel paper-holdings">
    <div className="rw-section-heading"><div><div className="eyebrow"><LocalizedText id="rw_invested_assets"/></div><h2><LocalizedText id="rw_positions"/></h2></div><span className="rw-tag">{portfolio?.positions.length ?? 0}</span></div>
    <div className="table-scroll" tabIndex={0}><table className="research-table"><thead><tr>{headings.map(key => <th key={key} scope="col"><LocalizedText id={key}/></th>)}</tr></thead><tbody>{portfolio?.positions.map(position => <tr key={position.symbol}>
      <th scope="row">{displaySymbol(position.market,position.symbol)}<small><LocalizedText>{position.market === 'us' ? 'U.S.' : 'Korea'}</LocalizedText></small></th>
      <td><LocalizedText>{value(position.market_value)}</LocalizedText></td><td>{position.quantity.toLocaleString(locale)}</td><td><LocalizedText>{value(position.average_cost)}</LocalizedText></td>
      <td><LocalizedText>{value(position.latest_price)}</LocalizedText><small>{position.price_observed_at ? new Date(position.price_observed_at).toLocaleString(locale) : <LocalizedText id="rw_price_unavailable"/>}</small></td>
      <td className={pnlClass(position.unrealized_pnl)}><LocalizedText>{value(position.unrealized_pnl)}</LocalizedText></td><td className={pnlClass(position.return_pct)}><LocalizedText>{finite(position.return_pct) ? `${formatValue(position.return_pct, undefined, locale)}%` : 'Unavailable'}</LocalizedText></td>
    </tr>)}</tbody></table></div>
    {!portfolio?.positions.length && <div className="rw-empty"><span className="rw-empty-mark" aria-hidden="true">—</span><h3><LocalizedText id={loading ? 'rw_loading_positions' : portfolio ? 'rw_no_positions' : 'rw_portfolio_unavailable'}/></h3><p><LocalizedText id={portfolio ? 'rw_empty_positions_note' : 'rw_retry_portfolio_note'}/></p></div>}
  </section>;
}

export function ActivityTable({ orders, currency, loading }: { orders: PaperOrder[]; currency: string; loading: boolean }) {
  const { locale } = useI18n();
  return <section className="history-panel rw-activity">
    <div className="rw-section-heading"><div><div className="eyebrow"><LocalizedText id="rw_execution_records"/></div><h2><LocalizedText id="rw_activity"/></h2></div><span className="rw-tag"><LocalizedText id="rw_simulated"/></span></div>
    <div className="table-scroll" tabIndex={0}><table className="research-table"><thead><tr>{(['rw_time','rw_symbol','rw_side','rw_quantity','rw_execution_price','rw_realized','rw_close_observation','fx_trade_conditions'] as const).map(key => <th key={key} scope="col"><LocalizedText id={key}/></th>)}</tr></thead><tbody>{orders.map(order => <tr key={order.id}>
      <th scope="row">{new Date(order.executed_at).toLocaleString(locale)}</th><td>{displaySymbol(order.market,order.symbol)}</td><td><span className={`rw-order-side rw-side-${order.side.toLowerCase()}`}><LocalizedText>{order.side}</LocalizedText></span></td><td>{order.quantity.toLocaleString(locale)}</td><td>{formatValue(order.execution_price, currency, locale)}</td><td className={pnlClass(order.realized_pnl)}>{formatValue(order.realized_pnl, currency, locale)}</td><td>{new Date(order.price_observed_at).toLocaleString(locale)}</td><td><ExecutionConditions detail={order.execution_details}/></td>
    </tr>)}</tbody></table></div>
    {Array.from(new Set(orders.map(order=>order.execution_details?.fx?.source).filter((source):source is string=>!!source))).map(source=><FxAttribution source={source} key={source}/>)}
    {!orders.length && <p className="comparison-note"><LocalizedText id={loading ? 'rw_loading_activity' : 'no_simulated_orders_recorded_accepted_orders_are_retained_rejecte_914aea'}/></p>}
  </section>;
}

export function RiskRoadmap() {
  const modules = [
    { title: 'rw_portfolio_risk' as const, description: 'rw_portfolio_risk_note' as const },
    { title: 'rw_portfolio_outlook' as const, description: 'rw_outlook_note' as const },
    { title: 'rw_diversification' as const, description: 'rw_diversification_note' as const },
    { title: 'rw_ai_advisor' as const, description: 'rw_ai_note' as const },
  ];
  return <section className="rw-roadmap"><div className="rw-section-heading"><h2><LocalizedText id="command_intelligence"/></h2><span className="rw-tag"><LocalizedText id="rw_not_available"/></span></div><p className="comparison-note"><LocalizedText id="rw_future_note"/></p><div className="rw-roadmap-grid">{modules.map(module => <article key={module.title} aria-disabled="true"><h3><LocalizedText id={module.title}/></h3><p><LocalizedText id={module.description}/></p><span className="rw-tag"><LocalizedText id="rw_not_available"/></span></article>)}</div></section>;
}

export function InvestmentSummary({investment}:{investment:Investment|null}) {
  const {locale,t}=useI18n();
  const displayValue=(amount:unknown,currency?:string,_locale?:string)=>typeof amount==='number'&&Number.isFinite(amount)?formatValue(amount,currency,locale):t('Unavailable');
  const metrics=[['capital_total',investment?.portfolio_value],['rw_available_cash',investment?.cash],['capital_invested',investment?.invested_value],['rw_total_pnl',investment?.total_pnl]] as const;
  return <section className="rw-summary-section">
    <div className="paper-summary">{metrics.map(([label,amount],index)=><article className={`rw-metric ${index===0?'rw-metric-primary':index===3?'rw-metric-pnl':''}`} key={label}><span><LocalizedText id={label}/></span><strong className={index===3?pnlClass(amount):''}>{displayValue(amount,'USD',locale)}</strong><small><LocalizedText id="capital_usd_base"/>{index===3 && investment?.total_return_pct!=null && <> · {displayValue(investment.total_return_pct,undefined,locale)}%</>}</small></article>)}</div>
    <div className="capital-native-balances"><span><LocalizedText id="capital_cash_balances"/></span><strong>{'USD'} {displayValue(investment?.cash_balances.USD,'USD',locale)}</strong><strong>{'KRW'} {displayValue(investment?.cash_balances.KRW,'KRW',locale)}</strong></div>
    <div className="capital-native-balances"><span><LocalizedText id="capital_native_invested"/></span><span><LocalizedText id="u_s_usd_e1d876"/> {displayValue(investment?.books.us.portfolio_value!=null?investment.books.us.portfolio_value-investment.books.us.cash:null,'USD',locale)}</span><span><LocalizedText id="korea_krw_07f26e"/> {displayValue(investment?.books.korea.portfolio_value!=null?investment.books.korea.portfolio_value-investment.books.korea.cash:null,'KRW',locale)}</span></div>
    <details className="capital-fx"><summary><LocalizedText id="capital_fx_latest"/>{isExchangeRate(investment?.fx?.source)&&<> · <LocalizedText id="fx_exchange_label"/></>} {investment?.fx ? ` · ${investment.fx.rate.toLocaleString(locale)}` : <LocalizedText id="capital_fx_unavailable"/>}</summary>{investment?.fx ? <p>{investment.fx.source} · <LocalizedText id="command_observation"/> {investment.fx.observation_timestamp || investment.fx.observation_date} · <LocalizedText id="capital_fx_retrieved"/> {new Date(investment.fx.retrieved_at).toLocaleString(locale)} · <LocalizedText id={investment.fx.selection_role==='primary'?'fx_validated_timestamp':'capital_fx_available'}/></p> : <p><LocalizedText>{investment?.fx_error || 'Validated USD/KRW FX is unavailable.'}</LocalizedText></p>}<p><LocalizedText id={isExchangeRate(investment?.fx?.source)?'fx_exchange_delayed':investment?.fx?.selection_role==='primary'?'fx_higher_frequency':'capital_fx_limits'}/></p>{investment?.fx?.selection_role==='fallback'&&<p><LocalizedText id="fx_daily_fallback"/></p>}</details><FxAttribution source={investment?.fx?.source}/>
    <div className="cost-performance">
      <span><LocalizedText id="cost_realized"/><strong>{displayValue(investment?.realized_pnl_usd_translated,'USD')}</strong></span>
      <span><LocalizedText id="cost_unrealized"/><strong>{displayValue(investment?.unrealized_pnl_usd_translated,'USD')}</strong></span>
      <span><LocalizedText id="cost_cumulative"/><strong>{displayValue(investment?.cumulative_fees_usd_translated,'USD')}</strong><small>{'USD'} {displayValue(investment?.cumulative_fees?.USD,'USD')} · {'KRW'} {displayValue(investment?.cumulative_fees?.KRW,'KRW')}</small></span>
      <span><LocalizedText id="cost_fx_cost"/><strong>{displayValue(investment?.fx_conversion_costs_usd,'USD')}</strong></span>
    </div><p className="comparison-note"><LocalizedText id="cost_pnl_translation"/></p>
    <p className="comparison-note"><LocalizedText id="capital_pnl_scope"/></p>
  </section>;
}

export function FxHistory({events}:{events:FxEvent[]}) {
  const {locale}=useI18n();
  return <section className="history-panel capital-fx-history"><div className="rw-section-heading"><h2><LocalizedText id="capital_fx_history"/></h2><span className="rw-tag"><LocalizedText id="rw_simulated"/></span></div><div className="table-scroll" tabIndex={0}><table className="research-table capital-fx-table"><thead><tr>{(['rw_time','rw_symbol','rw_execution_price','capital_conversion','capital_usd_remaining','capital_krw_remaining','capital_position_after','fx_execution_snapshot'] as const).map(key=><th key={key}><LocalizedText id={key}/></th>)}</tr></thead><tbody>{events.map(event=><tr key={event.order_id}><td>{new Date(event.executed_at).toLocaleString(locale)}</td><td>{displaySymbol(event.market,event.symbol)}</td><td>{formatValue(event.execution_price/(event.market==='us'?100:1),event.market==='us'?'USD':'KRW',locale)}</td><td>{formatValue(event.from_minor/(event.from_currency==='USD'?100:1),event.from_currency,locale)} → {formatValue(event.to_minor/(event.to_currency==='USD'?100:1),event.to_currency,locale)}</td><td>{formatValue(event.usd_cash_after/100,'USD',locale)}</td><td>{formatValue(event.krw_cash_after,'KRW',locale)}</td><td>{event.quantity_after}</td><td>{event.effective_rate || event.rate}<small><LocalizedText id="cost_reference_fx"/> {event.rate} · {event.spread_bps ?? '0'} {'bps'}</small><small>{event.observation_date} · {event.source}</small></td></tr>)}</tbody></table></div>{Array.from(new Set(events.map(event=>event.source))).map(source=><FxAttribution source={source} key={source}/>)}{!events.length&&<p className="comparison-note"><LocalizedText id="capital_fx_no_events"/></p>}</section>;
}

export default function PortfolioWorkspace({ view, user, books, investment=null, loading, csrf, onExecuted }: { view: Market | 'all'; user: User; books: PortfolioBooks; investment?:Investment|null; loading: boolean; csrf: string; onExecuted: () => void }) {
  const markets: Market[] = view==='all' ? ['us','korea'] : [view];
  return <>
    <div className="command-workstation"><div className="command-portfolio">
      <InvestmentSummary investment={investment}/>
      <StressAnalytics userId={user.id} valuationAt={investment?.observed_at}/>
      <FxExposure investment={investment}/>
      {investment && !investment.valuation_complete && <p className="api-notice"><LocalizedText id="capital_incomplete"/></p>}
      <div className="rw-analytics-grid"><PortfolioPerformance performance={investment?.performance ?? []} portfolio={null} currency="USD" loading={loading}/></div>
      {markets.map(market=><div className="unified-book-detail" key={market}>
        <div className="unified-book-heading"><h2><LocalizedText>{market==='us'?'U.S. · USD':'Korea · KRW'}</LocalizedText></h2><span><LocalizedText id="rw_daily_closes"/></span></div>
        <PositionsTable portfolio={books[market]?.portfolio ?? null} currency={market==='us'?'USD':'KRW'} loading={loading}/>
        <ActivityTable orders={books[market]?.orders ?? []} currency={market==='us'?'USD':'KRW'} loading={loading}/>
      </div>)}
      <FxHistory events={investment?.fx_conversions ?? []}/>
    </div><div className="command-trade-rail"><TradeTicket key={user.id} portfolios={{us:books.us?.portfolio ?? null,korea:books.korea?.portfolio ?? null}} csrf={csrf} userId={user.id} onExecuted={onExecuted}/></div></div>

  </>;
}

export function ExecutionConditions({detail}:{detail?:ExecutionDetails|null}) {
  const {locale}=useI18n();
  if(!detail?.costs)return <LocalizedText id="fx_evidence_unavailable"/>;
  const scale=detail.market==='us'?100:1;
  const rows=[['cost_gross',formatValue(detail.costs.gross_minor/scale,detail.currency,locale)],['cost_commission',formatValue(detail.costs.commission_minor/scale,detail.currency,locale)],['cost_transaction_tax',formatValue(detail.costs.transaction_tax_minor/scale,detail.currency,locale)],['cost_regulatory',formatValue(detail.costs.regulatory_fee_minor/scale,detail.currency,locale)],['fx_historical_usd',detail.execution_attribution?.gross_usd!=null?formatValue(Number(detail.execution_attribution.gross_usd),'USD',locale):'Unavailable']] as const;
  return <details className="fx-execution-detail"><summary><LocalizedText id="fx_trade_conditions"/></summary><dl>{rows.map(([key,value])=><div key={key}><dt><LocalizedText id={key}/></dt><dd><LocalizedText>{value}</LocalizedText></dd></div>)}</dl>{detail.fx&&<><p><LocalizedText id="fx_execution_snapshot"/> {detail.fx.rate.toLocaleString(locale)} · {detail.fx.source} · {detail.fx.observation_timestamp||detail.fx.observation_date} · <LocalizedText id="fx_validated_at_execution"/></p><p><LocalizedText id="capital_fx_retrieved"/> {new Date(detail.fx.retrieved_at).toLocaleString(locale)}</p><p><LocalizedText id="cost_fx_spread"/> {detail.from_currency?detail.fx_spread_bps:'0'} {'bps'} · <LocalizedText id="cost_applied_fx"/> {detail.effective_fx_rate??'—'} · <LocalizedText id="cost_fx_cost"/> {formatValue(Number(detail.fx_cost_usd_exact||'0'),'USD',locale)}</p>{detail.from_currency&&<p>{detail.from_currency} → {detail.to_currency} · {'USD'} {formatValue(detail.fx_usd_cents/100,'USD',locale)} · {'KRW'} {formatValue(detail.fx_krw,'KRW',locale)}</p>}{detail.side==='SELL'&&detail.execution_attribution?.available&&<dl>{([['fx_acquisition_basis',detail.execution_attribution.purchase_fx_basis],['fx_native_pnl',detail.execution_attribution.native_realized_stock_pnl],['fx_translation',detail.execution_attribution.fx_effect_usd],['fx_sale_net',detail.execution_attribution.net_realized_usd]] as const).map(([key,value])=><div key={key}><dt><LocalizedText id={key}/></dt><dd>{value==null?'—':formatValue(Number(value),key==='fx_acquisition_basis'?undefined:key==='fx_native_pnl'?detail.currency:'USD',locale)}</dd></div>)}</dl>}<FxDelay fx={detail.fx}/><FxAttribution source={detail.fx.source}/></>}</details>;
}

export function FxExposure({investment}:{investment:Investment|null}) {
  const {locale}=useI18n();const data=investment?.fx_attribution;
  const usd=(v:unknown)=><LocalizedText>{formatValue(v,'USD',locale)}</LocalizedText>;
  return <section className="history-panel fx-exposure"><div className="rw-section-heading"><h2><LocalizedText id="fx_exposure_title"/></h2></div><p className="comparison-note"><LocalizedText id="fx_stress_context"/></p>{data?.available?<>
    <div className="cost-performance">{([['fx_krw_exposure',data.krw_exposure_usd],['fx_native_effect',data.native_investment_effect_usd],['fx_translation',data.fx_translation_effect_usd],['fx_reconciled',data.reconciled_total_usd_pnl]] as const).map(([key,value])=><span key={key}><LocalizedText id={key}/><strong>{usd(value)}</strong></span>)}</div>
    <p><LocalizedText id="fx_krw_share"/> {formatValue(data.krw_exposure_pct,undefined,locale)}% · <LocalizedText id="fx_cash_effect"/> {usd(data.krw_cash_fx_unrealized_usd)}</p>
    <p className="comparison-note"><LocalizedText id="fx_reconciliation"/> {usd(data.native_investment_effect_usd)} + {usd(data.fx_translation_effect_usd)} − {usd(data.trading_costs_usd)} − {usd(data.fx_conversion_costs_usd)} + {usd(data.rounding_residual_usd)} = {usd(data.reconciled_total_usd_pnl)}</p>
    {data.positions.filter(p=>p.market==='korea').map(position=><details key={position.symbol} className="fx-position-detail"><summary>{displaySymbol(position.market,position.symbol)} · <LocalizedText id="fx_position_detail"/></summary><dl>{([
      ['fx_purchase_price',formatValue(position.average_purchase_price,'KRW',locale)],['rw_current_price',formatValue(investment?.books.korea.positions.find(p=>p.symbol===position.symbol)?.latest_price,'KRW',locale)],
      ['fx_acquisition_basis',formatValue(position.average_acquisition_fx,undefined,locale)],['capital_fx_latest',formatValue(position.current_fx,undefined,locale)],['fx_change',`${formatValue(position.fx_change_pct,undefined,locale)}%`],
      ['fx_native_pnl',formatValue(position.native_stock_pnl,'KRW',locale)],['fx_native_effect',formatValue(position.native_effect_usd,'USD',locale)],['fx_translation',formatValue(position.fx_effect_usd,'USD',locale)],
      ['fx_position_costs',formatValue(position.purchase_costs_usd,'USD',locale)],['fx_position_total',formatValue(position.total_usd_pnl,'USD',locale)]
    ] as const).map(([key,value])=><div key={key}><dt><LocalizedText id={key}/></dt><dd>{value}</dd></div>)}</dl><p className="comparison-note"><LocalizedText id="fx_position_basis_note"/></p></details>)}
  </>:<p className="comparison-note"><LocalizedText id="fx_evidence_unavailable"/></p>}</section>;
}
