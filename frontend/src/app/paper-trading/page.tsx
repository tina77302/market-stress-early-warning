'use client';

import { LocalizedText, useI18n } from '../i18n/provider';


import { useEffect, useState } from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import AccountPanel from './AccountPanel';
import TradeTicket from './TradeTicket';
import { ApiError, Market, PaperOrder, PerformancePoint, Portfolio, User, value as formatValue, workspace } from './types';
import DataHealthNotice from '../components/DataHealthNotice';
import { Latest, signal, fmt } from '../components/market-data';

function MarketRiskContext() {
  const { t, locale } = useI18n();

  const [us, setUS] = useState<Latest | null>(null), [korea, setKorea] = useState<Latest | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const base = '';
    async function current(path: string) { const response = await fetch(`${base}${path}`, { signal: controller.signal }); if (!response.ok) throw new Error('Market context unavailable'); return response.json(); }
    void Promise.allSettled([current('/api/latest'), current('/api/korea/latest')]).then(([a, b]) => { if (controller.signal.aborted) return; setUS(a.status === 'fulfilled' ? a.value : null); setKorea(b.status === 'fulfilled' ? b.value : null); });
    return () => controller.abort();
  }, []);
  return <section className="history-panel paper-risk"><h2><LocalizedText id="market_risk_context_528908"/></h2><DataHealthNotice market="us" latest={us}/><DataHealthNotice market="korea" latest={korea}/><div className="paper-risk-signals"><div><span><LocalizedText id="u_s_7a3239"/></span><strong><LocalizedText>{signal('us', us)}</LocalizedText></strong><small><LocalizedText id="score_489f48" after/><LocalizedText>{fmt(us?.risk_score_10d, 1)}</LocalizedText> / 100 · <LocalizedText>{us?.last_updated || 'Observation unavailable'}</LocalizedText></small></div><div><span><LocalizedText id="korea_4e8bd0"/></span><strong><LocalizedText>{signal('korea', korea)}</LocalizedText></strong><small><LocalizedText id="score_489f48" after/><LocalizedText>{fmt(korea?.risk_score_10d, 1)}</LocalizedText> / 100 · <LocalizedText>{korea?.last_updated || 'Observation unavailable'}</LocalizedText></small></div></div><p className="comparison-note"><LocalizedText id="independent_market_stress_signals_provide_market_context_not_secu_ede585"/></p></section>;
}
export default function PaperTradingPage() {
  const { t, locale } = useI18n();
  const value = (number: unknown, currency?: string) => formatValue(number, currency, locale);

  const [user, setUser] = useState<User | null>(null), [csrf, setCsrf] = useState('');
  const [checking, setChecking] = useState(true), [market, setMarket] = useState<Market>('us');
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null), [orders, setOrders] = useState<PaperOrder[]>([]), [performance, setPerformance] = useState<PerformancePoint[]>([]);
  const [loading, setLoading] = useState(false), [error, setError] = useState(''), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void workspace<{ user: User; csrf_token: string }>('auth/me', { signal: controller.signal }).then(result => {setUser(result.user);setCsrf(result.csrf_token);}).catch(error => {if (!controller.signal.aborted && !(error instanceof ApiError && error.status === 401)) setError(error.message);}).finally(() => {if (!controller.signal.aborted) setChecking(false);});
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    setLoading(true);setError('');setPortfolio(null);setOrders([]);setPerformance([]);
    async function load() {
      try {
        const session = await workspace<{ user: User; csrf_token: string }>('auth/me', { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (session.user.id !== user?.id) { setUser(session.user); setCsrf(session.csrf_token); return; }
        const data = await workspace<Portfolio>(`paper/portfolio?market=${market}`, { signal: controller.signal });
        const [activity, chart] = await Promise.all([workspace<{ data: PaperOrder[] }>(`paper/orders?market=${market}`, { signal: controller.signal }), workspace<{ data: PerformancePoint[] }>(`paper/performance?market=${market}`, { signal: controller.signal })]);
        if (controller.signal.aborted) return;
        setCsrf(session.csrf_token);setPortfolio(data);setOrders(activity.data);setPerformance(chart.data);
      } catch (error) { if (!controller.signal.aborted) { if (error instanceof ApiError && error.status === 401) {setUser(null);setCsrf('');} setError(error instanceof Error ? error.message : 'Portfolio unavailable.'); } }
      finally {if (!controller.signal.aborted) setLoading(false);}
    }
    void load();return () => controller.abort();
  }, [user, market, refresh]);
  async function logout() {
    setError('');
    try { await workspace('auth/logout', { body: {}, csrf });setUser(null);setCsrf('');setPortfolio(null);setOrders([]);setPerformance([]);window.dispatchEvent(new Event('mri-auth-changed')); }
    catch (error) {setError(error instanceof Error ? error.message : 'Logout unavailable.');}
  }
  const currency = market === 'us' ? 'USD' : 'KRW';
  const summaries = [['PORTFOLIO VALUE', value(portfolio?.portfolio_value, currency)], ['CASH', value(portfolio?.cash, currency)], ["TODAY’S P&L", value(portfolio?.today_pnl, currency)], ['TOTAL RETURN', portfolio?.total_return_pct == null ? 'Unavailable' : `${value(portfolio.total_return_pct)}%`]];
  const invested = portfolio?.portfolio_value != null ? portfolio.portfolio_value - portfolio.cash : null;
  const share = portfolio?.portfolio_value && invested !== null ? Math.max(0,Math.min(100,invested / portfolio.portfolio_value * 100)) : null;
  return <div className="risk-home detail-page paper-page"><div className="home-content">
    <header className="detail-heading"><div className="eyebrow"><LocalizedText id="paper_trading_simulated_only_cdf219"/></div><h1><LocalizedText id="virtual_portfolio_cd7fbc"/></h1><p><LocalizedText id="a_private_practice_workspace_using_virtual_cash_and_completed_mar_448136"/></p>{user && <div className="paper-session"><span><LocalizedText>{user.email}</LocalizedText></span><button className="paper-secondary" onClick={logout} disabled={!csrf}><LocalizedText id="log_out_6e78c9"/></button></div>}</header>
    <LocalizedText>{checking && <div className="api-notice" role="status"><LocalizedText id="checking_your_session_81e98c"/></div>}<LocalizedText></LocalizedText>{error && <div className="api-notice" role="alert"><LocalizedText>{error}<LocalizedText></LocalizedText>{user && <button onClick={() => setRefresh(value => value + 1)}><LocalizedText id="retry_workspace_348ff4"/></button>}</LocalizedText></div>}</LocalizedText>
    {!checking && !user && <AccountPanel onAuthenticated={setUser}/>}
    {user && <>
      <div className="paper-workspace-heading"><nav className="market-switcher" aria-label={t("Portfolio currency account")}><button aria-pressed={market === 'us'} onClick={() => setMarket('us')}><LocalizedText id="u_s_usd_e1d876"/></button><button aria-pressed={market === 'korea'} onClick={() => setMarket('korea')}><LocalizedText id="korea_krw_07f26e"/></button></nav><button className="paper-secondary" onClick={() => setRefresh(value => value + 1)} disabled={loading}><LocalizedText>{loading ? 'Refreshing…' : 'Refresh valuations'}</LocalizedText></button></div><p className="comparison-note"><LocalizedText id="independent_currency_accounts_no_fx_conversion_or_cross_currency__b4ee47"/></p>
      <section className="paper-summary" aria-label={t("Portfolio summary")}>{summaries.map(([label, amount]) => <div key={label}><span><LocalizedText>{label}</LocalizedText></span><strong><LocalizedText>{amount}</LocalizedText></strong></div>)}</section>
      <div className="paper-pnl"><span><LocalizedText id="realized_p_l_2a8946" after/><strong><LocalizedText>{value(portfolio?.realized_pnl, currency)}</LocalizedText></strong></span><span><LocalizedText id="unrealized_p_l_73c67e" after/><strong><LocalizedText>{value(portfolio?.unrealized_pnl, currency)}</LocalizedText></strong></span></div><p className="comparison-note"><LocalizedText>{portfolio?.today_pnl_note || 'Today’s P&L requires a prior-day recorded valuation.'}</LocalizedText></p>
      {portfolio && !portfolio.valuation_complete && <div className="api-notice" role="status"><LocalizedText id="some_prices_are_unavailable_or_stale_portfolio_value_return_and_u_a14ae9"/></div>}
      <section className="history-panel"><div className="chart-heading"><h2><LocalizedText id="portfolio_performance_26ee77"/></h2><span><LocalizedText>{currency}</LocalizedText><LocalizedText id="recorded_valuations_9b2c36" before/></span></div><div className="history-chart">{performance.length > 1 ? <ResponsiveContainer width="100%" height="100%"><LineChart data={performance}><CartesianGrid stroke="#203445" vertical={false}/><XAxis dataKey="observed_at" tickFormatter={date => new Date(date).toLocaleTimeString(locale, {hour:'2-digit',minute:'2-digit'})} minTickGap={50} tick={{fill:'#8ca7bd',fontSize:12}}/><YAxis domain={['auto','auto']} tickFormatter={number => new Intl.NumberFormat(locale,{notation:'compact'}).format(number)} tick={{fill:'#8ca7bd',fontSize:12}}/><Tooltip labelFormatter={date => new Date(date).toLocaleString(locale)} formatter={(amount: number) => [value(amount,currency),t('Portfolio value')]} contentStyle={{background:'#0b1a27',border:'1px solid #34566d',fontSize:14}}/><Line dataKey="value" stroke="#83bfc9" strokeWidth={2} dot={performance.length < 20} isAnimationActive={false}/></LineChart></ResponsiveContainer> : <div className="chart-empty"><LocalizedText>{loading ? 'Loading observed valuations…' : 'Performance begins with your account’s first recorded valuation.'}</LocalizedText><small><LocalizedText id="additional_visits_and_fills_record_actual_observations_no_histori_7c82f9"/></small></div>}</div>{share !== null && <div className="paper-allocation"><span><LocalizedText id="securities_4bd973" after/><LocalizedText>{share.toFixed(1)}</LocalizedText><LocalizedText id="cash_182ce9" after/><LocalizedText>{(100-share).toFixed(1)}</LocalizedText>%</span><div aria-hidden="true"><i style={{width:`${share}%`}}/></div></div>}</section>
      <div className="paper-columns"><section className="history-panel paper-holdings"><h2><LocalizedText id="holdings_8c8a4f"/></h2><div className="table-scroll"><table className="research-table"><thead><tr>{['Symbol','Market','Quantity','Average Cost','Latest Close','Market Value','Unrealized P&L','Return'].map(label => <th key={label} scope="col"><LocalizedText>{label}</LocalizedText></th>)}</tr></thead><tbody>{portfolio?.positions.map(position => <tr key={position.symbol}><th scope="row"><LocalizedText>{position.symbol}</LocalizedText></th><td><LocalizedText>{position.market === 'us' ? 'U.S.' : 'Korea'}</LocalizedText></td><td><LocalizedText>{position.quantity}</LocalizedText></td><td><LocalizedText>{value(position.average_cost,currency)}</LocalizedText></td><td><LocalizedText>{value(position.latest_price,currency)}</LocalizedText><small><LocalizedText>{position.price_observed_at ? new Date(position.price_observed_at).toLocaleDateString(locale) : 'Price unavailable'}</LocalizedText></small></td><td><LocalizedText>{value(position.market_value,currency)}</LocalizedText></td><td className={position.unrealized_pnl != null ? position.unrealized_pnl >= 0 ? 'paper-gain' : 'paper-loss' : ''}><LocalizedText>{value(position.unrealized_pnl,currency)}</LocalizedText></td><td><LocalizedText>{position.return_pct == null ? 'Unavailable' : `${value(position.return_pct)}%`}</LocalizedText></td></tr>)}</tbody></table></div>{!portfolio?.positions.length && <p className="comparison-note"><LocalizedText>{loading ? 'Loading holdings…' : 'No holdings in this currency account yet.'}</LocalizedText></p>}</section><TradeTicket key={`${user.id}:${market}`} market={market} portfolio={portfolio} csrf={csrf} userId={user.id} onExecuted={() => setRefresh(value => value + 1)}/></div>
      <section className="history-panel"><h2><LocalizedText id="recent_activity_order_history_8bd1eb"/></h2><div className="table-scroll"><table className="research-table"><thead><tr>{['Submitted','Security','Side','Shares','Simulated Fill','Realized P&L','Close Observation'].map(label => <th key={label}><LocalizedText>{label}</LocalizedText></th>)}</tr></thead><tbody>{orders.map(order => <tr key={order.id}><th scope="row"><LocalizedText>{new Date(order.executed_at).toLocaleString(locale)}</LocalizedText></th><td><LocalizedText>{order.symbol}</LocalizedText></td><td><LocalizedText>{order.side}</LocalizedText></td><td><LocalizedText>{order.quantity}</LocalizedText></td><td><LocalizedText>{value(order.execution_price,currency)}</LocalizedText></td><td><LocalizedText>{value(order.realized_pnl,currency)}</LocalizedText></td><td><LocalizedText>{new Date(order.price_observed_at).toLocaleString(locale)}</LocalizedText></td></tr>)}</tbody></table></div>{!orders.length && <p className="comparison-note"><LocalizedText id="no_simulated_orders_recorded_accepted_orders_are_retained_rejecte_914aea"/></p>}</section>
    </>}
    <MarketRiskContext/><p className="model-disclaimer"><LocalizedText id="simulated_only_no_real_money_brokerage_connection_margin_leverage_708f04"/></p>
  </div></div>;
}
