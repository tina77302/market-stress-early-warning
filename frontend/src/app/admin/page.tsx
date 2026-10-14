'use client';

import { LocalizedText, useI18n } from '../i18n/provider';


import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ApiError, User, workspace } from '../paper-trading/types';

interface RefreshHistory { markets: Record<string,{status:string; last_known_good_date:string|null; expected_observation_date:string|null; scheduler:{status:string;heartbeat_fresh:boolean}}>; jobs: {job_id:string;market:string;started_at:string;status:string;error_message:string|null;snapshot_published:boolean;attempts:{series:string;provider:string;status:string;attempt_count:number;latest_observation_date:string|null;retrieved_at:string|null;error_message:string|null}[]}[] }
interface Overview {
  total_users: number; total_portfolios: number; total_simulated_orders: number;
  accounts_with_unexpired_sessions: number; current_account: User;
  health: { api: string; database: string }; observed_at: string; session_note: string;
}
interface ManagedUser extends User { created_at: string; portfolio_count: number; portfolio_status: string }
interface UserPage { data: ManagedUser[]; total: number; limit: number; offset: number }

export default function AdminPage() {
  const { t, locale } = useI18n();

  const [dataHealth,setDataHealth]=useState<RefreshHistory|null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<UserPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [offset, setOffset] = useState(0), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);setDataHealth(null);setOverview(null);setUsers(null);setError('');setDenied(null);
    void Promise.all([workspace<Overview>('admin/overview', { signal: controller.signal }), workspace<UserPage>(`admin/users?limit=50&offset=${offset}`, { signal: controller.signal }),workspace<RefreshHistory>('admin/data-health',{signal:controller.signal})]).then(([summary, users, health]) => {if (!controller.signal.aborted) {setOverview(summary);setUsers(users);setDataHealth(health);}}).catch(error => {if (!controller.signal.aborted) {if (error instanceof ApiError && [401,403].includes(error.status)) setDenied(error.status);else setError(error instanceof Error ? error.message : 'Administration unavailable.');}}).finally(() => {if (!controller.signal.aborted) setLoading(false);});
    const changed = () => {setOverview(null);setUsers(null);setRefresh(value => value + 1);};
    window.addEventListener('mri-auth-changed',changed);
    window.addEventListener('focus',changed);
    return () => {controller.abort();window.removeEventListener('mri-auth-changed',changed);window.removeEventListener('focus',changed);};
  }, [offset,refresh]);
  return <div className="risk-home detail-page research-page"><div className="home-content">
    <header className="detail-heading"><div className="eyebrow"><LocalizedText id="admin_console_read_only_a97bf3"/></div><h1><LocalizedText id="system_overview_09b853"/></h1><p><LocalizedText id="account_administration_and_aggregate_simulated_portfolio_activity_0d6cd9"/></p><div className="market-subnav"><Link href="/"><LocalizedText id="market_intelligence_973e3d"/></Link><Link href="/paper-trading"><LocalizedText id="my_virtual_portfolio_3c0269"/></Link></div></header>
    {loading && <div className="api-notice" role="status"><LocalizedText id="verifying_administrator_authorization_19a7e3"/></div>}
    {denied && <section className="research-section"><h2><LocalizedText>{denied === 401 ? 'Login required' : 'Administrator access required'}</LocalizedText></h2><p><LocalizedText>{denied === 401 ? 'Log in with your existing account to continue.' : 'Your account is a normal user; administrative data is restricted.'}</LocalizedText></p><Link className="blue-button" href="/paper-trading"><LocalizedText id="open_account_workspace_279685"/></Link></section>}
    {error && <div className="api-notice" role="alert"><LocalizedText>{error}</LocalizedText><button onClick={() => setRefresh(value => value + 1)}><LocalizedText id="retry_9f5cd8"/></button></div>}
    {dataHealth && <section className="research-section"><h2><LocalizedText id="admin_market_data_health"/></h2><dl className="sample-summary">{Object.entries(dataHealth.markets).map(([market,health])=><div key={market}><dt><LocalizedText>{market==='us'?'U.S.':'Korea'}</LocalizedText></dt><dd><LocalizedText id={health.status==='ERROR'?'error_data_health':undefined}>{health.status}</LocalizedText></dd><p><LocalizedText id="last_observation_a4f8bb"/>: <LocalizedText>{health.last_known_good_date || 'Unavailable'}</LocalizedText></p><p><LocalizedText id="scheduler_health_label"/>: <LocalizedText>{health.scheduler.status}</LocalizedText></p></div>)}</dl><details><summary><LocalizedText id="refresh_job_history"/></summary>{dataHealth.jobs.map(job=><details key={job.job_id}><summary><LocalizedText>{job.market==='us'?'U.S.':'Korea'}</LocalizedText> · <LocalizedText id={job.status==='ERROR'?'error_data_health':undefined}>{job.status}</LocalizedText> · {new Date(job.started_at).toLocaleString(locale)}</summary><p>{job.job_id}</p>{job.error_message && <p className="paper-error"><LocalizedText>{job.error_message}</LocalizedText></p>}<div className="table-scroll"><table className="research-table"><thead><tr>{['Series','Provider','Status','Attempt','Last Observation','Retrieved at','Error'].map(label=><th key={label}><LocalizedText>{label}</LocalizedText></th>)}</tr></thead><tbody>{job.attempts.map((attempt,index)=><tr key={index}><td><LocalizedText>{attempt.series}</LocalizedText></td><td><LocalizedText>{attempt.provider}</LocalizedText></td><td><LocalizedText id={attempt.status==='ERROR'?'error_data_health':undefined}>{attempt.status}</LocalizedText></td><td>{attempt.attempt_count}</td><td>{attempt.latest_observation_date || '—'}</td><td>{attempt.retrieved_at ? new Date(attempt.retrieved_at).toLocaleString(locale):'—'}</td><td><LocalizedText>{attempt.error_message || '—'}</LocalizedText></td></tr>)}</tbody></table></div></details>)}</details></section>}
    {overview && <>
      <section className="research-section"><h2><span>01</span><LocalizedText id="system_summary_debe55"/></h2><dl className="sample-summary">{[['Registered users',overview.total_users],['Paper portfolios',overview.total_portfolios],['Simulated orders',overview.total_simulated_orders],['Accounts with valid sessions',overview.accounts_with_unexpired_sessions]].map(([label,count]) => <div key={label}><dt><LocalizedText>{label}</LocalizedText></dt><dd><LocalizedText>{Number(count).toLocaleString(locale)}</LocalizedText></dd></div>)}</dl><p><LocalizedText>{overview.session_note}</LocalizedText></p><dl className="research-metadata"><div><dt><LocalizedText id="authenticated_administrator_658be1"/></dt><dd><LocalizedText>{overview.current_account.email}</LocalizedText> · <LocalizedText>{overview.current_account.role}</LocalizedText></dd></div><div><dt><LocalizedText id="api_database_0a7147"/></dt><dd><LocalizedText>{overview.health.api}</LocalizedText> / <LocalizedText>{overview.health.database}</LocalizedText></dd></div><div><dt><LocalizedText id="observed_2e159b"/></dt><dd><LocalizedText>{new Date(overview.observed_at).toLocaleString(locale)}</LocalizedText></dd></div></dl></section>
      <section className="research-section"><div className="chart-heading"><h2><span>02</span><LocalizedText id="user_management_7d5918"/></h2><button className="paper-secondary" onClick={() => setRefresh(value => value + 1)}><LocalizedText id="refresh_56e3ba"/></button></div><div className="table-scroll"><table className="research-table"><thead><tr>{['User ID','Email','Role','Created','Portfolio status'].map(label => <th key={label} scope="col"><LocalizedText>{label}</LocalizedText></th>)}</tr></thead><tbody>{users?.data.map(user => <tr key={user.id}><th scope="row"><LocalizedText>{user.id}</LocalizedText></th><td><LocalizedText>{user.email}</LocalizedText></td><td><LocalizedText>{user.role}</LocalizedText></td><td><LocalizedText>{new Date(user.created_at).toLocaleString(locale)}</LocalizedText></td><td><LocalizedText>{user.portfolio_status === 'present' ? `${user.portfolio_count} portfolios` : 'No portfolios'}</LocalizedText></td></tr>)}</tbody></table></div>{users && <div className="admin-pagination"><button className="paper-secondary" disabled={offset === 0 || loading} onClick={() => setOffset(value => Math.max(0,value - 50))}><LocalizedText id="previous_50f942"/></button><span><LocalizedText>{users.total ? `${offset+1}–${Math.min(offset+users.data.length,users.total)}` : '0'}</LocalizedText><LocalizedText id="of_de04fa" before after/><LocalizedText>{users.total}</LocalizedText><LocalizedText id="users_5b7dcd" before/></span><button className="paper-secondary" disabled={offset+users.data.length >= users.total || loading} onClick={() => setOffset(value => value + 50)}><LocalizedText id="next_bc9819"/></button></div>}<p><LocalizedText id="read_only_access_administrative_views_cannot_submit_trades_for_an_715c51"/></p></section>
    </>}
  </div></div>;
}
