'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Activity, ArrowDown, ArrowRight, ArrowUp, BarChart3, BookOpen, ChevronRight, Clock3, Database, FlaskConical, Globe2, Home, Lightbulb, ShieldAlert } from 'lucide-react';
import { Area, CartesianGrid, ComposedChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
interface Latest { last_updated: string; risk_score_10d: number | null; spy_price: number | null; vix_level: number | null; baa_treasury_spread: number | null; market_stress_index: number | null }
interface Historical { date: string; spy: number | null; vix: number | null; baa_treasury_spread: number | null; risk_score_xgboost: number | null }
interface Shap { date: string; top_drivers: { feature: string; shap_value: number }[] }
type Range = '1Y' | '3Y' | '5Y' | 'ALL';
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const format = (value: unknown, digits = 2, prefix = '', suffix = '') => finite(value) ? `${prefix}${value.toFixed(digits)}${suffix}` : '--';

function MarketGlobe() {
  return <div className="market-globe" aria-label="Global markets illustration: U.S. model available; Korea coming soon" role="img">
    <svg viewBox="0 0 520 360" aria-hidden="true">
      <defs>
        <radialGradient id="home-ocean" cx="32%" cy="28%"><stop stopColor="#123d61"/><stop offset=".7" stopColor="#071d31"/><stop offset="1" stopColor="#030b14"/></radialGradient>
        <radialGradient id="home-halo"><stop stopColor="#36a7e8" stopOpacity=".48"/><stop offset="1" stopColor="#218ad8" stopOpacity="0"/></radialGradient>
        <clipPath id="home-earth-clip"><circle cx="260" cy="180" r="151"/></clipPath>
        <filter id="home-glow"><feGaussianBlur stdDeviation="6"/></filter>
      </defs>
      <g className="globe-network" fill="none" stroke="#4d93bd" strokeWidth=".7">
        <path d="M18 212Q260 12 500 202M42 85Q250 265 485 73M36 278Q258 76 493 265"/>
        <ellipse cx="260" cy="180" rx="224" ry="90" transform="rotate(-22 260 180)"/>
        <path d="M65 60L130 91 194 43 302 63 450 112M25 246L108 271 203 311 364 296 480 237" strokeDasharray="2 6"/>
        {[[65,60],[130,91],[302,63],[450,112],[108,271],[364,296],[480,237]].map(([cx,cy]) => <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="2" fill="#77bce3" stroke="none"/>)}
      </g>
      <circle className="globe-atmosphere" cx="260" cy="180" r="179" fill="url(#home-halo)"/>
      <circle cx="260" cy="180" r="151" fill="url(#home-ocean)" stroke="#28618b" strokeWidth="1.5"/>
      <g clipPath="url(#home-earth-clip)" fill="none" stroke="#2b6487" strokeOpacity=".35">
        {[45, 90, 130].map(r => <ellipse key={r} cx="260" cy="180" rx={r} ry="151"/>)}
        {[85, 125, 180, 235, 275].map(y => <ellipse key={y} cx="260" cy={y} rx="151" ry="24"/>)}
      </g>
      <g clipPath="url(#home-earth-clip)" fill="#0b2a40" stroke="#3b7aa5" strokeWidth="1.2" strokeLinejoin="round">
        <path d="M115 100l25-18 23-6 18-24 41-5 23 15-7 21-23 5-9 17-19 3-4 21-13 7 5 17 20 9 2 17-12 8-18-17-10-27-26-9-12-23z"/>
        <path d="M188 191l24-10 27 20 12 25-8 17-8 33-18 24-10-16 2-30-11-19-4-24z"/>
        <path d="M239 40l22-9 18 14-8 33-17 8-16-17z"/>
        <path d="M282 101l17-18 23 3 8-14 34 7 19 21 34 9 14 31-15 20-21-4-11 20-19-11-9-27-18-2-12-17-12 9-19-7-8 9-15-9z"/>
        <path d="M280 140l28-7 30 24 7 27-19 43-19 21-15-15-3-31-20-32z"/>
        <path d="M371 245l27-12 28 17-7 20-31 5-20-13z"/>
        <path d="M384 162l5 18-4 14-5-18z"/>
      </g>
      <g clipPath="url(#home-earth-clip)" fill="none" stroke="#5dbdeb" strokeWidth=".8" strokeOpacity=".35">
        <path d="M166 138Q268 31 382 147M166 138Q225 154 303 126M303 126Q361 154 388 251M166 138Q160 201 217 237" strokeDasharray="3 5"/>
        <circle cx="303" cy="126" r="2" fill="#91d3f2"/><circle cx="217" cy="237" r="2" fill="#91d3f2"/><circle cx="388" cy="251" r="2" fill="#91d3f2"/>
      </g>
      <circle className="market-node-pulse node-us" cx="166" cy="138" r="10" fill="none" stroke="#46e0bc"/>
      <circle className="market-node-pulse node-korea" cx="382" cy="147" r="10" fill="none" stroke="#edc26d"/>
      <path d="M83 116Q132 104 166 138" fill="none" stroke="#1de0b2" strokeWidth="1.5"/>
      <path d="M382 147Q409 173 453 177" fill="none" stroke="#e6af48" strokeWidth="1.5"/>
      <circle cx="166" cy="138" r="17" fill="#1de0b2" filter="url(#home-glow)"/><circle cx="166" cy="138" r="4" fill="#9affdf"/>
      <circle cx="382" cy="147" r="15" fill="#f4b844" filter="url(#home-glow)"/><circle cx="382" cy="147" r="4" fill="#ffe2a0"/>
    </svg>
    <span className="globe-label globe-us"><span>🇺🇸</span> U.S.</span><span className="globe-label globe-kr"><span>🇰🇷</span> Korea <small>SOON</small></span>
  </div>;
}

function Sparkline({ data, field }: { data: Historical[]; field: 'spy' | 'vix' | 'baa_treasury_spread' }) {
  if (!data.some(point => finite(point[field]))) return <div className="spark-empty">Historical data unavailable</div>;
  return <div className="metric-spark" aria-hidden="true"><ResponsiveContainer width="100%" height="100%"><LineChart data={data}><YAxis hide domain={['dataMin', 'dataMax']}/><Line dataKey={field} dot={false} stroke="#2ccab5" strokeWidth={1.6} isAnimationActive={false}/></LineChart></ResponsiveContainer></div>;
}

export default function MarketRiskPage() {
  const [latest, setLatest] = useState<Latest | null>(null);
  const [history, setHistory] = useState<Historical[]>([]);
  const [shap, setShap] = useState<Shap | null>(null);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [range, setRange] = useState<Range>('3Y');
  const [insightsOpen, setInsightsOpen] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setErrors([]);
    async function request(path: string) {
      const response = await fetch(`${API_URL}${path}`, { signal: controller.signal });
      if (!response.ok) throw new Error(path);
      return response.json();
    }
    async function load() {
      const results = await Promise.allSettled([request('/api/latest'), request('/api/historical?days=10000'), request('/api/shap')]);
      if (controller.signal.aborted) return;
      const [current, historical, drivers] = results;
      setLatest(current.status === 'fulfilled' ? current.value : null);
      setHistory(historical.status === 'fulfilled' && Array.isArray(historical.value.data) ? [...historical.value.data].sort((a: Historical, b: Historical) => a.date.localeCompare(b.date)) : []);
      setShap(drivers.status === 'fulfilled' && Array.isArray(drivers.value.top_drivers) ? drivers.value : null);
      setErrors(results.flatMap((result, i) => result.status === 'rejected' ? [['Market snapshot', 'Historical data', 'SHAP drivers'][i]] : []));
      setLoading(false);
    }
    void load();
    return () => controller.abort();
  }, [refresh]);
  const score = latest?.risk_score_10d;
  const level = !finite(score) ? '--' : score >= 70 ? 'HIGH' : score >= 50 ? 'ELEVATED' : score >= 30 ? 'WATCH' : 'LOW';
  const tone = level === 'LOW' ? 'green' : level === 'WATCH' ? 'amber' : level === '--' ? 'muted' : 'red';
  const filtered = useMemo(() => {
    if (range === 'ALL' || !history.length) return history;
    const start = new Date(history[history.length - 1].date);
    start.setFullYear(start.getFullYear() - Number(range[0]));
    return history.filter(point => new Date(point.date) >= start);
  }, [history, range]);
  const metrics = [
    { label: 'SPY', value: format(latest?.spy_price, 2, '$'), field: 'spy' as const },
    { label: 'VIX', value: format(latest?.vix_level), field: 'vix' as const },
    { label: 'Baa–Treasury', value: format(latest?.baa_treasury_spread, 2, '', '%'), field: 'baa_treasury_spread' as const },
  ];
  const groups = [
    { label: 'Stock Market', icon: BarChart3, match: (f: string) => f.startsWith('SPY_') },
    { label: 'Market Volatility', icon: Activity, match: (f: string) => f.startsWith('VIX_') },
    { label: 'Credit Conditions', icon: Database, match: (f: string) => /^(Credit_|BAA_)/.test(f) },
  ];
  return <div className="risk-home">
    <header className="home-nav">
      <Link href="/" className="home-brand"><ShieldAlert size={27}/><span>MARKET RISK INTELLIGENCE</span><small>AI EARLY WARNING SYSTEM</small></Link>
      <nav aria-label="Main navigation"><Link href="/" aria-current="page" className="active"><Home size={16}/>Overview</Link><Link href="/us"><span>🇺🇸</span>U.S. Market</Link><a href="#korea"><span>🇰🇷</span>Korea Market</a><Link href="/validation"><BarChart3 size={16}/>Model Validation</Link><Link href="/methodology"><FlaskConical size={16}/>Methodology</Link></nav>
    </header>
    <div className="home-content">
      <section className="home-hero">
        <div className="hero-copy"><div className="eyebrow">GLOBAL MARKETS · FORWARD-LOOKING INTELLIGENCE</div><h1>Market stress.<br/><span>An earlier warning.</span></h1><h2>MARKET STRESS EARLY WARNING</h2><p>Will broad financial-market stress emerge within the next 10 trading days?</p><Link href="/methodology" className="blue-button"><BookOpen size={15}/>How it works<ArrowRight size={15}/></Link></div>
        <MarketGlobe/>
        <aside className="hero-snapshot"><div className="observation"><Clock3 size={15}/><span>LAST MARKET OBSERVATION<strong>{latest?.last_updated || '--'}</strong></span><span className={`data-status ${!latest ? 'offline' : ''}`}><i/>{loading ? 'Loading' : latest ? 'API connected' : 'Unavailable'}</span></div><div className="snapshot-panel"><div className="eyebrow">KEY INDICATORS · U.S. MARKET</div><div className="snapshot-metrics">{metrics.map(metric => <div key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong><Sparkline data={history.slice(-40)} field={metric.field}/></div>)}</div><small>Latest observation · sparklines show last 40 OOS observations</small></div></aside>
      </section>
      {errors.length > 0 && <div className="api-notice" role="status">{errors.join(', ')} unavailable. <button onClick={() => setRefresh(value => value + 1)} disabled={loading}>{loading ? 'Retrying…' : 'Retry connection'}</button></div>}
      <section className="market-grid" aria-label="Market overview">
        <article className={`market-card us-card tone-${tone}`}><div className="city-image us-image"/><div className="market-card-content"><div className="card-heading"><h2><span className="flag">🇺🇸</span> U.S. MARKET<ChevronRight size={18}/></h2><span className={`risk-badge ${tone}`}>{level === '--' ? 'UNAVAILABLE' : `${level} RISK`}</span></div><div className="us-card-body"><div className="score-block"><span className="score-label">10-Day Risk Score</span><div className={`risk-number ${tone}`}>{format(score, 1)}<small>/ 100</small></div><p>Forward-looking market<br/>stress warning.</p><div className="current-msi">CURRENT STRESS · MSI <strong>{format(latest?.market_stress_index, 2)}</strong></div></div><div className="us-metrics"><div className="eyebrow">MARKET SNAPSHOT</div>{metrics.map(metric => <div key={metric.label}><span>{metric.label === 'Baa–Treasury' ? 'Credit Spread' : metric.label}</span><strong>{metric.value}</strong></div>)}<Link href="/us" className="market-button">Explore U.S. Market<ArrowRight size={17}/></Link></div></div><div className="score-footnote">LOW &lt;30 <span>WATCH 30–&lt;50</span><span>ELEVATED 50–&lt;70</span><span>HIGH ≥70</span></div></div></article>
        <article className="market-card korea-card" id="korea"><div className="city-image korea-image"/><div className="market-card-content"><div className="card-heading"><h2><span className="flag">🇰🇷</span> KOREA MARKET</h2><span className="risk-badge amber">COMING SOON</span></div><div className="korea-body"><span className="eyebrow">THE NEXT MARKET HORIZON</span><h3>Local markets.<br/>The same rigorous lens.</h3><p>Korean-market stress model<br/>pending data and validation.</p></div><div className="korea-preview"><span>KOSPI <small>--</small></span><span>VKOSPI <small>--</small></span><span>Credit <small>--</small></span><span className="pending"><Clock3 size={14}/>Model in development</span></div></div></article>
      </section>
      <section className="drivers-panel"><div className="drivers-title"><h2>CURRENT RISK DRIVERS</h2><p>Leading SHAP contributions{shap?.date ? ` · ${shap.date}` : ''}</p></div><div className="driver-groups">{groups.map(group => {
        const drivers = shap?.top_drivers.filter(driver => group.match(driver.feature) && finite(driver.shap_value)) ?? [];
        const net = drivers.reduce((sum, driver) => sum + driver.shap_value, 0);
        const color = !drivers.length || net === 0 ? 'muted' : net > 0 ? 'red' : 'green';
        const Icon = group.icon;
        return <div className={`driver channel-${color}`} key={group.label}><span className="driver-icon"><Icon size={20}/></span><div><span>{group.label}</span><strong className={color}>{!drivers.length ? '--' : net === 0 ? '→ Neutral' : <>{net > 0 ? <ArrowUp size={13}/> : <ArrowDown size={13}/>}Net Risk-{net > 0 ? 'Increasing' : 'Reducing'}</>}</strong></div></div>;
      })}</div><small>Net effect of leading factors on model output, not probability changes.</small></section>
      <section className="history-grid">
        <article className="history-panel"><div className="chart-heading"><div><h2><span className="blue-dot"/>HISTORICAL MARKET STRESS</h2><p>U.S. · XGBoost 10-Day Risk Score vs SPY</p></div><div className="range-buttons" aria-label="Historical chart time range">{(['1Y', '3Y', '5Y', 'ALL'] as Range[]).map(value => <button key={value} onClick={() => setRange(value)} aria-pressed={range === value} className={range === value ? 'selected' : ''}>{value}</button>)}</div></div><div className="chart-legend"><span><i/>10-Day Risk Score · left axis / 100</span><span><i/>SPY · right axis USD</span></div><div className="history-chart">{filtered.length ? <ResponsiveContainer width="100%" height="100%"><ComposedChart data={filtered} margin={{ top: 12, right: 0, bottom: 0, left: -18 }}><defs><linearGradient id="home-risk-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#1dd6b0" stopOpacity={.3}/><stop offset="100%" stopColor="#1dd6b0" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#1a2a37" vertical={false}/><XAxis dataKey="date" tickFormatter={date => date.slice(0, 4)} minTickGap={55} tick={{ fill: '#7890a4', fontSize: 11 }} axisLine={false} tickLine={false}/><YAxis yAxisId="risk" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fill: '#7890a4', fontSize: 11 }} axisLine={false} tickLine={false}/><YAxis yAxisId="spy" orientation="right" domain={['auto', 'auto']} tick={{ fill: '#7890a4', fontSize: 11 }} axisLine={false} tickLine={false}/><Tooltip contentStyle={{ background: '#0b1a27f2', border: '1px solid #3c5b70', borderRadius: 10, color: '#e4eef6', boxShadow: '0 12px 32px #0008', padding: '12px 16px', fontSize: 12, backdropFilter: 'blur(12px)' }} formatter={(value: number, name: string) => [finite(value) ? value.toFixed(name === 'SPY' ? 2 : 1) : '--', name === 'SPY' ? 'SPY (USD)' : '10-Day Risk Score / 100']}/><Area yAxisId="risk" type="linear" dataKey="risk_score_xgboost" name="10-Day Risk Score" stroke="#47e1bf" strokeWidth={2.2} fill="url(#home-risk-gradient)" isAnimationActive={false}/><Line yAxisId="spy" type="linear" dataKey="spy" name="SPY" stroke="#eab451" strokeWidth={1.7} dot={false} isAnimationActive={false}/></ComposedChart></ResponsiveContainer> : <div className="chart-empty"><BarChart3 size={30}/><span>{loading ? 'Loading historical observations…' : 'Historical data unavailable'}</span><small>Real walk-forward out-of-sample data appears here.</small></div>}</div><div className="chart-note"><Database size={12}/>Purged walk-forward OOS predictions · Risk Score is not calibrated event probability.</div></article>
        <aside className="insights-panel" id="insights"><div className="insights-heading"><h2>KEY INSIGHTS</h2><Lightbulb size={18}/></div><div className="insight"><span>01</span><div><h3>A warning, not a price forecast.</h3><p>The model assesses broad U.S. financial-market stress over the next 10 trading days.</p></div></div><div className="insight"><span>02</span><div><h3>Two distinct perspectives.</h3><p>MSI measures current stress. The Risk Score looks ahead.</p></div></div><div className="insight"><span>03</span><div><h3>Validation comes first.</h3><p>Historical scores use walk-forward OOS predictions. Korea awaits data and validation.</p></div></div><Link href="/validation">Explore the evidence<ArrowRight size={15}/></Link></aside>
      </section>
      <section className="bottom-grid" aria-label="Explore the project"><Link href="/validation" className="bottom-card"><span className="bottom-icon blue"><BarChart3/></span><div><h2>Model Validation</h2><p>Out-of-sample performance<br/>and historical event analysis.</p></div><ChevronRight/></Link><Link href="/methodology" className="bottom-card"><span className="bottom-icon purple"><BookOpen/></span><div><h2>Methodology</h2><p>Data, target definition<br/>and modeling approach.</p></div><ChevronRight/></Link><button className="bottom-card" onClick={() => setInsightsOpen(value => !value)} aria-expanded={insightsOpen} aria-controls="expanded-insights"><span className="bottom-icon gold"><Lightbulb/></span><div><h2>Key Insights</h2><p>Understand the current assessment<br/>and what the signals mean.</p></div><ChevronRight/></button></section>
      {insightsOpen && <section id="expanded-insights" className="expanded-insights"><h2>Understanding the assessment</h2><p>{finite(score) ? `The latest U.S. Risk Score is ${score.toFixed(1)} / 100 (${level}).` : 'The latest U.S. Risk Score is unavailable.'} The score assesses broad stress events, not stock-price direction. SHAP channels aggregate only the leading factors returned by the API; factors within a channel can offset one another.</p><Link href="/methodology">Read the methodology <ArrowRight size={14}/></Link></section>}
      <footer className="home-footer"><span><Globe2 size={13}/>MARKET RISK INTELLIGENCE</span><span>U.S. stress early warning · 10 trading days · XGBoost</span></footer>
    </div>
  </div>;
}
