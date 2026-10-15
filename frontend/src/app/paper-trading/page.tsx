'use client';

import { LocalizedText, useI18n } from '../i18n/provider';


import { useEffect, useState } from 'react';
import AccountPanel from './AccountPanel';
import PortfolioWorkspace from './PortfolioWorkspace';
import CurrentMarketRisk from './MarketRiskPanel';
import './paper-trading.css';
import { ApiError, Market, PaperOrder, PerformancePoint, Portfolio, User, workspace } from './types';

export default function PaperTradingPage() {
  const { t, locale } = useI18n();

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
  const priceDates = portfolio?.positions.flatMap(position => position.price_observed_at ? [position.price_observed_at] : []).sort() ?? [];
  return <div className="risk-home detail-page paper-page"><div className="home-content">
    <header className="detail-heading rw-header">
      <div><div className="eyebrow"><LocalizedText id="rw_paper_trading"/><span className="rw-tag"><LocalizedText id="rw_no_real_money"/></span></div><h1><LocalizedText id="rw_paper_trading"/></h1><h2 className="command-subtitle"><LocalizedText id="rw_title"/></h2><p><LocalizedText id="command_motto"/></p><p className="command-support"><LocalizedText id="command_support"/></p></div>
      {user && <div className="paper-session"><span className="rw-identity">{user.username || user.email || '—'}</span><button className="paper-secondary" onClick={logout} disabled={!csrf}><LocalizedText id="log_out_6e78c9"/></button></div>}
    </header>
    <section className="command-market-status" aria-label={t('Market status · latest validated observations')}><CurrentMarketRisk market="us" compact/><CurrentMarketRisk market="korea" compact/></section>
    {checking && <div className="api-notice" role="status"><LocalizedText id="checking_your_session_81e98c"/></div>}
    {error && <div className="api-notice" role="alert"><LocalizedText>{error}</LocalizedText>{user && <button onClick={() => setRefresh(value => value + 1)}><LocalizedText id="retry_workspace_348ff4"/></button>}</div>}
    {!checking && !user && <div className="rw-anonymous"><AccountPanel onAuthenticated={setUser}/><CurrentMarketRisk market={market}/></div>}
    {user && <>
      <div className="rw-workspace-toolbar"><div className="paper-workspace-heading"><nav className="market-switcher" aria-label={t('Portfolio currency account')}><button aria-pressed={market === 'us'} onClick={() => setMarket('us')}><LocalizedText id="u_s_usd_e1d876"/></button><button aria-pressed={market === 'korea'} onClick={() => setMarket('korea')}><LocalizedText id="korea_krw_07f26e"/></button></nav><button className="paper-secondary" onClick={() => setRefresh(value => value + 1)} disabled={loading}><LocalizedText>{loading ? 'Refreshing…' : 'Refresh valuations'}</LocalizedText></button></div>
        <div className="rw-workspace-meta"><span>{currency}</span><span><LocalizedText id="rw_daily_closes"/></span>{portfolio && <span className={portfolio.valuation_complete ? '' : 'amber'}><LocalizedText id={portfolio.valuation_complete ? 'rw_valuation_complete' : 'rw_valuation_incomplete'}/></span>}{priceDates.length > 0 && <span><LocalizedText id="rw_latest_position_close" after/>{new Date(priceDates[priceDates.length - 1]).toLocaleString(locale)}</span>}</div>
        <p className="comparison-note"><LocalizedText id="independent_currency_accounts_no_fx_conversion_or_cross_currency__b4ee47"/></p>
      </div>
      <div aria-busy={loading} className="rw-workspace"><PortfolioWorkspace market={market} user={user} portfolio={portfolio} performance={performance} orders={orders} loading={loading} csrf={csrf} onExecuted={() => setRefresh(value => value + 1)}/></div>
    </>}
    <p className="model-disclaimer"><LocalizedText id="simulated_only_no_real_money_brokerage_connection_margin_leverage_708f04"/></p>
  </div></div>;
}
