'use client';

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { LocalizedText, useI18n } from '../i18n/provider';
import { finite } from '../components/market-data';
import TradeTicket from './TradeTicket';
import { Market, PaperOrder, PerformancePoint, Portfolio, User, value as formatValue, displaySymbol } from './types';

const pnlClass = (number: number | null | undefined) => !finite(number) || number === 0 ? '' : number > 0 ? 'paper-gain' : 'paper-loss';

export function PortfolioSummary({ portfolio, currency }: { portfolio: Portfolio | null; currency: string }) {
  const { locale } = useI18n();
  const value = (amount: unknown) => formatValue(amount, currency, locale);
  const totalPnl = finite(portfolio?.portfolio_value) ? portfolio.portfolio_value - portfolio.starting_cash : null;
  const invested = finite(portfolio?.portfolio_value) ? portfolio.portfolio_value - portfolio.cash : null;
  const metrics = [
    { label: 'rw_total_equity' as const, amount: portfolio?.portfolio_value, primary: true },
    { label: 'rw_available_cash' as const, amount: portfolio?.cash },
    { label: 'rw_invested_value' as const, amount: invested },
    { label: 'rw_total_pnl' as const, amount: totalPnl, pnl: true },
  ];
  return <section className="rw-summary-section">
    <div className="paper-summary">{metrics.map(metric => <article className={`rw-metric ${metric.primary ? 'rw-metric-primary' : ''}`} key={metric.label}>
      <span><LocalizedText id={metric.label}/></span>
      <strong className={metric.pnl ? pnlClass(metric.amount) : ''}><LocalizedText>{value(metric.amount)}</LocalizedText></strong>
      <small>{metric.pnl ? <><LocalizedText>{finite(portfolio?.total_return_pct) ? `${formatValue(portfolio.total_return_pct, undefined, locale)}%` : 'Unavailable'}</LocalizedText><LocalizedText id="rw_since_inception" before/></> : <LocalizedText id={metric.primary ? 'rw_equity_note' : metric.label === 'rw_available_cash' ? 'rw_cash_note' : 'rw_invested_note'}/>}</small>
    </article>)}</div>
    <div className="paper-pnl">{[
      { label: 'realized_p_l_2a8946' as const, amount: portfolio?.realized_pnl },
      { label: 'unrealized_p_l_73c67e' as const, amount: portfolio?.unrealized_pnl },
      { label: 'rw_today_pnl' as const, amount: portfolio?.today_pnl },
    ].map(item => <span key={item.label}><LocalizedText id={item.label}/><strong className={pnlClass(item.amount)}><LocalizedText>{value(item.amount)}</LocalizedText></strong></span>)}</div>
    <p className="comparison-note"><LocalizedText>{portfolio?.today_pnl_note || 'Today’s P&L requires a prior-day recorded valuation.'}</LocalizedText></p>
  </section>;
}

export function PortfolioPerformance({ performance, portfolio, currency, loading }: { performance: PerformancePoint[]; portfolio: Portfolio | null; currency: string; loading: boolean }) {
  const { t, locale } = useI18n();
  const value = (amount: unknown) => formatValue(amount, currency, locale);
  const invested = finite(portfolio?.portfolio_value) ? portfolio.portfolio_value - portfolio.cash : null;
  const share = portfolio?.portfolio_value && invested !== null ? Math.max(0, Math.min(100, invested / portfolio.portfolio_value * 100)) : null;
  return <section className="history-panel rw-performance">
    <div className="rw-section-heading"><div><div className="eyebrow"><LocalizedText id="rw_account_history"/></div><h2><LocalizedText id="portfolio_performance_26ee77"/></h2></div><span className="rw-tag">{currency}</span></div>
    <div className="rw-chart-legend"><span><i aria-hidden="true"/><LocalizedText id="rw_total_equity"/></span><span><LocalizedText id="rw_recorded_only"/></span><span className="command-overlay-note"><LocalizedText id="command_overlay"/></span></div>
    <div className="history-chart">{performance.length ? <ResponsiveContainer width="100%" height="100%"><LineChart data={performance} margin={{ top: 12, right: 12, bottom: 10, left: 0 }}>
      <CartesianGrid stroke="#252e38" vertical={false}/><XAxis dataKey="observed_at" tickFormatter={date => new Date(date).toLocaleDateString(locale, { month: 'short', day: 'numeric' })} minTickGap={65} tick={{ fill: '#8d9ba8', fontSize: 12 }} axisLine={false} tickLine={false}/>
      <YAxis domain={['auto','auto']} width={70} tickFormatter={number => new Intl.NumberFormat(locale, { notation: 'compact' }).format(number)} tick={{ fill: '#8d9ba8', fontSize: 12 }} axisLine={false} tickLine={false}/>
      <Tooltip labelFormatter={date => new Date(date).toLocaleString(locale)} formatter={(amount: number) => [value(amount), t('Total equity')]} contentStyle={{ background: '#151c24', border: '1px solid #35404c', borderRadius: 8, fontSize: 14 }}/>
      <Line type="linear" dataKey="value" stroke="#6ba9ef" strokeWidth={2} dot={performance.length < 20} activeDot={{ r: 4 }} isAnimationActive={false}/>
    </LineChart></ResponsiveContainer> : <div className="chart-empty"><LocalizedText>{loading ? 'Loading observed valuations…' : 'Performance begins with your account’s first recorded valuation.'}</LocalizedText><small><LocalizedText id="additional_visits_and_fills_record_actual_observations_no_histori_7c82f9"/></small></div>}</div>
    <div className="rw-performance-footer"><span><LocalizedText id="rw_history_limit"/></span>{performance.length > 0 && <span><LocalizedText id="rw_latest_record" after/>{new Date(performance[performance.length - 1].observed_at).toLocaleString(locale)}</span>}</div>
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
    <div className="table-scroll" tabIndex={0}><table className="research-table"><thead><tr>{(['rw_time','rw_symbol','rw_side','rw_quantity','rw_execution_price','rw_realized','rw_close_observation'] as const).map(key => <th key={key} scope="col"><LocalizedText id={key}/></th>)}</tr></thead><tbody>{orders.map(order => <tr key={order.id}>
      <th scope="row">{new Date(order.executed_at).toLocaleString(locale)}</th><td>{displaySymbol(order.market,order.symbol)}</td><td><span className={`rw-order-side rw-side-${order.side.toLowerCase()}`}><LocalizedText>{order.side}</LocalizedText></span></td><td>{order.quantity.toLocaleString(locale)}</td><td>{formatValue(order.execution_price, currency, locale)}</td><td className={pnlClass(order.realized_pnl)}>{formatValue(order.realized_pnl, currency, locale)}</td><td>{new Date(order.price_observed_at).toLocaleString(locale)}</td>
    </tr>)}</tbody></table></div>
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

export default function PortfolioWorkspace({ market, user, portfolio, performance, orders, loading, csrf, onExecuted }: { market: Market; user: User; portfolio: Portfolio | null; performance: PerformancePoint[]; orders: PaperOrder[]; loading: boolean; csrf: string; onExecuted: () => void }) {
  const currency = market === 'us' ? 'USD' : 'KRW';
  return <>
    <div className="command-workstation"><div className="command-portfolio">
    <PortfolioSummary portfolio={portfolio} currency={currency}/>
    {portfolio && !portfolio.valuation_complete && <div className="api-notice" role="status"><LocalizedText id="some_prices_are_unavailable_or_stale_portfolio_value_return_and_u_a14ae9"/></div>}
    <div className="rw-analytics-grid"><PortfolioPerformance performance={performance} portfolio={portfolio} currency={currency} loading={loading}/></div>
    <PositionsTable portfolio={portfolio} currency={currency} loading={loading}/></div><div className="command-trade-rail"><TradeTicket key={`${user.id}:${market}`} market={market} portfolio={portfolio} csrf={csrf} userId={user.id} onExecuted={onExecuted}/></div></div>
    <ActivityTable orders={orders} currency={currency} loading={loading}/><RiskRoadmap/>
  </>;
}
