'use client';

import { LocalizedText, useI18n } from '../i18n/provider';


import { useEffect, useState } from 'react';
import AccountPanel from './AccountPanel';
import PortfolioWorkspace from './PortfolioWorkspace';
import CurrentMarketRisk, { MarketRiskProvider } from './MarketRiskPanel';
import './paper-trading.css';
import { ApiError, Investment, Market, PortfolioBook, PortfolioBooks, Portfolio, PaperOrder, PerformancePoint, User, workspace } from './types';

export default function PaperTradingPage() {
  const { t } = useI18n();

  const [user, setUser] = useState<User | null>(null), [csrf, setCsrf] = useState('');
  const [checking, setChecking] = useState(true), [view, setView] = useState<Market | 'all'>('all');
  const [books,setBooks] = useState<PortfolioBooks>({});
  const [investment,setInvestment] = useState<Investment|null>(null);
  const [loading, setLoading] = useState(false), [error, setError] = useState(''), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void workspace<{ user: User; csrf_token: string }>('auth/me', { signal: controller.signal }).then(result => {setUser(result.user);setCsrf(result.csrf_token);}).catch(error => {if (!controller.signal.aborted && !(error instanceof ApiError && error.status === 401)) setError(error.message);}).finally(() => {if (!controller.signal.aborted) setChecking(false);});
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    setLoading(true);setError('');setBooks({});setInvestment(null);
    async function load() {
      try {
        const session = await workspace<{ user: User; csrf_token: string }>('auth/me', { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (session.user.id !== user?.id) { setUser(session.user); setCsrf(session.csrf_token); return; }
        const total=await workspace<Investment>('paper/investment',{signal:controller.signal});
        const results=await Promise.all((['us','korea'] as const).map(async market=>{
          const activity=await workspace<{data:PaperOrder[]}>(`paper/orders?market=${market}`,{signal:controller.signal});
          return {market,book:{portfolio:total.books[market],orders:activity.data,performance:[]} as PortfolioBook};
        }));
        if(controller.signal.aborted)return;
        const loaded:PortfolioBooks={};for(const result of results)loaded[result.market]=result.book;
        setCsrf(session.csrf_token);setBooks(loaded);setInvestment(total);
      } catch (error) { if (!controller.signal.aborted) { if (error instanceof ApiError && error.status === 401) {setUser(null);setCsrf('');} setError(error instanceof Error ? error.message : 'Portfolio unavailable.'); } }
      finally {if (!controller.signal.aborted) setLoading(false);}
    }
    void load();return () => controller.abort();
  }, [user, refresh]);
  useEffect(()=>{
    if(!user)return;
    const controller=new AbortController();let running=false;
    const check=async()=>{
      if(running || document.visibilityState==='hidden')return;
      running=true;
      try {
        const current=await workspace<{fx:{id:string}}>('paper/fx',{signal:controller.signal});
        if(!controller.signal.aborted && current.fx.id!==investment?.fx?.id)setRefresh(value=>value+1);
      } catch {if(!controller.signal.aborted && investment?.fx)setRefresh(value=>value+1);}
      finally {running=false;}
    };
    const timer=setInterval(()=>void check(),60000);window.addEventListener('focus',check);
    return()=>{controller.abort();clearInterval(timer);window.removeEventListener('focus',check);};
  },[user,investment?.fx]);
  async function logout() {
    setError('');
    try { await workspace('auth/logout', { body: {}, csrf });setUser(null);setCsrf('');setBooks({});setInvestment(null);window.dispatchEvent(new Event('mri-auth-changed')); }
    catch (error) {setError(error instanceof Error ? error.message : 'Logout unavailable.');}
  }
  return <MarketRiskProvider><div className="risk-home detail-page paper-page"><div className="home-content">
    <div className="command-heading-row">
      <header className="detail-heading rw-header">
        <div className="command-title-line"><h1><LocalizedText id="rw_paper_trading"/></h1><span className="rw-tag"><LocalizedText id="rw_no_real_money"/></span></div>
        <h2 className="command-subtitle"><LocalizedText id="rw_title"/></h2>
        <p><LocalizedText id="command_motto"/></p>
        {user && <div className="paper-session"><span className="rw-identity">{user.username || user.email || '—'}</span><button className="paper-secondary" onClick={logout} disabled={!csrf}><LocalizedText id="log_out_6e78c9"/></button></div>}
      </header>
      <section className="command-market-status" aria-label={t('Market status · latest validated observations')}>
        <div className={view === 'us' ? 'command-selected-market' : ''}><CurrentMarketRisk market="us" compact/></div>
        <div className={view === 'korea' ? 'command-selected-market' : ''}><CurrentMarketRisk market="korea" compact/></div>
      </section>
    </div>
    {checking && <div className="api-notice" role="status"><LocalizedText id="checking_your_session_81e98c"/></div>}
    {error && <div className="api-notice" role="alert"><LocalizedText>{error}</LocalizedText>{user && <button onClick={() => setRefresh(value => value + 1)}><LocalizedText id="retry_workspace_348ff4"/></button>}</div>}
    {!checking && !user && <div className="rw-anonymous"><AccountPanel onAuthenticated={setUser}/><CurrentMarketRisk market="us"/></div>}
    {user && <>
      <div className="rw-workspace-toolbar"><div className="paper-workspace-heading"><nav className="market-switcher" aria-label={t('Portfolio view')}>
        <button aria-pressed={view==='all'} onClick={()=>setView('all')}><LocalizedText id="unified_all"/></button>
        <button aria-pressed={view==='us'} onClick={()=>setView('us')}><LocalizedText id="u_s_usd_e1d876"/></button>
        <button aria-pressed={view==='korea'} onClick={()=>setView('korea')}><LocalizedText id="korea_krw_07f26e"/></button>
      </nav><button className="paper-secondary" onClick={()=>setRefresh(value=>value+1)} disabled={loading}><LocalizedText>{loading?'Refreshing…':'Refresh valuations'}</LocalizedText></button></div>
      <span className="comparison-note"><LocalizedText id="capital_single_base"/></span></div>
      <div aria-busy={loading} className="rw-workspace"><PortfolioWorkspace view={view} user={user} books={books} investment={investment} loading={loading} csrf={csrf} onExecuted={() => setRefresh(value => value + 1)}/></div>
    </>}
    <p className="model-disclaimer"><LocalizedText id="simulated_only_no_real_money_brokerage_connection_margin_leverage_708f04"/></p>
  </div></div></MarketRiskProvider>;
}
