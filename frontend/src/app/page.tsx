'use client';
import { modelAvailable, signal } from './components/market-data';

import { LocalizedText, useI18n } from './i18n/provider';


import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Activity, ArrowDown, ArrowRight, ArrowUp, BarChart3, BookOpen, ChevronRight, Clock3, Database, Globe2, Lightbulb } from 'lucide-react';
import { Area, CartesianGrid, ComposedChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import CrossMarketSnapshot, { GlobalAssessment, ModelDisclaimer } from './components/CrossMarketSnapshot';

const API_URL = '';
interface Latest { data_health?: import('./components/market-data').DataHealth; last_updated: string; risk_score_10d: number | null; spy_price: number | null; vix_level: number | null; baa_treasury_spread: number | null; market_stress_index: number | null }

interface KoreaLatest {
  data_health?: import('./components/market-data').DataHealth;
  last_updated: string;
  risk_score_10d: number | null;
  kospi200: number | null;
  vkospi: number | null;
  korea_credit_spread: number | null;
  korea_credit_spread_bp: number | null;
  market_stress_index: number | null;
  stress_threshold: number | null;
  is_stress_event: boolean;
  warning_threshold: number | null;
  warning_active: boolean;
}

interface Historical { date: string; spy: number | null; vix: number | null; baa_treasury_spread: number | null; risk_score_xgboost: number | null }
interface Shap { date: string; top_drivers: { feature: string; shap_value: number }[] }
type Range = '1Y' | '3Y' | '5Y' | 'ALL';
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const format = (value: unknown, digits = 2, prefix = '', suffix = '') => finite(value) ? `${prefix}${value.toFixed(digits)}${suffix}` : '--';

function MarketGlobe() {
  const { t, locale } = useI18n();

  return <div className="market-globe" aria-label={t("Global markets illustration: U.S. and Korea market-stress models available")} role="img">
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
    <span className="globe-label globe-us"><span>🇺🇸</span><LocalizedText id="u_s_7a3239" before/></span><span className="globe-label globe-kr"><span>🇰🇷</span><LocalizedText id="korea_4e8bd0" before/></span>
  </div>;
}

function Sparkline({ data, field }: { data: Historical[]; field: 'spy' | 'vix' | 'baa_treasury_spread' }) {
  const { t, locale } = useI18n();

  if (!data.some(point => finite(point[field]))) return <div className="spark-empty"><LocalizedText id="historical_data_unavailable_46b250"/></div>;
  return <div className="metric-spark" aria-hidden="true"><ResponsiveContainer width="100%" height="100%"><LineChart data={data}><YAxis hide domain={['dataMin', 'dataMax']}/><Line dataKey={field} dot={false} stroke="#2ccab5" strokeWidth={1.6} isAnimationActive={false}/></LineChart></ResponsiveContainer></div>;
}

export default function MarketRiskPage() {
  const { t, locale } = useI18n();

  const [latest, setLatest] = useState<Latest | null>(null);
  const [koreaLatest, setKoreaLatest] = useState<KoreaLatest | null>(null);
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
      const results = await Promise.allSettled([
        request('/api/latest'),
        request('/api/historical?days=10000'),
        request('/api/shap'),
        request('/api/korea/latest'),
      ]);
      if (controller.signal.aborted) return;
      const [current, historical, drivers, korea] = results;
      setLatest(current.status === 'fulfilled' ? current.value : null);
      setHistory(historical.status === 'fulfilled' && Array.isArray(historical.value.data) ? [...historical.value.data].sort((a: Historical, b: Historical) => a.date.localeCompare(b.date)) : []);
      setShap(drivers.status === 'fulfilled' && current.status === 'fulfilled' && drivers.value.date === current.value.last_updated && Array.isArray(drivers.value.top_drivers) ? drivers.value : null);
      setKoreaLatest(korea.status === 'fulfilled' ? korea.value : null);
      setErrors(
        results.flatMap((result, i) =>
          result.status === 'rejected'
            ? [['U.S. market snapshot', 'Historical data', 'SHAP drivers', 'Korea market snapshot'][i]]
            : []
        )
      );
      setLoading(false);
    }
    void load();
    return () => controller.abort();
  }, [refresh]);
  const score = modelAvailable(latest) ? latest!.risk_score_10d : null;
  const level = !finite(score) ? '--' : score >= 70 ? 'HIGH' : score >= 50 ? 'ELEVATED' : score >= 30 ? 'WATCH' : 'LOW';
  const tone = level === 'LOW' ? 'green' : level === 'WATCH' ? 'amber' : level === '--' ? 'muted' : 'red';

  const koreaScore = modelAvailable(koreaLatest) ? koreaLatest!.risk_score_10d : null;
  const koreaWarning = signal('korea', koreaLatest) === 'WARNING';
  const koreaTone = !finite(koreaScore) ? 'muted' : koreaWarning ? 'red' : 'green';
  const koreaStatus = !finite(koreaScore)
    ? 'UNAVAILABLE'
    : koreaWarning
      ? 'WARNING'
      : 'BELOW WARNING';

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
    <div className="home-content">
      <section className="home-hero">
        <div className="hero-copy"><div className="eyebrow"><LocalizedText id="global_markets_forward_looking_intelligence_7a56d1"/></div><h1><LocalizedText id="market_stress_c09ca4"/><br/><span><LocalizedText id="an_earlier_warning_18baf8"/></span></h1><h2><LocalizedText id="market_stress_early_warning_72b129"/></h2><p><LocalizedText id="will_broad_financial_market_stress_emerge_within_the_next_10_trad_4cf995"/></p><Link href="/methodology" className="blue-button"><BookOpen size={15}/><LocalizedText id="how_it_works_1dd6a1"/><ArrowRight size={15}/></Link></div>
        <MarketGlobe/>
        <aside className="hero-snapshot"><div className="observation"><Clock3 size={15}/><span><LocalizedText id="u_s_last_market_observation_9a6f66"/><strong><LocalizedText>{latest?.last_updated || '--'}</LocalizedText></strong></span><span className={`data-status ${!modelAvailable(latest) ? 'offline' : ''}`}><i/><LocalizedText id={!loading && latest?.data_health?.status==='ERROR'?'error_data_health':undefined}>{loading ? 'Loading' : latest?.data_health?.is_current ? 'API connected' : latest?.data_health?.status || 'Unavailable'}</LocalizedText></span></div><div className="snapshot-panel"><div className="eyebrow"><LocalizedText id="key_indicators_u_s_market_431446"/></div><div className="snapshot-metrics">{metrics.map(metric => <div key={metric.label}><span><LocalizedText>{metric.label}</LocalizedText></span><strong><LocalizedText>{metric.value}</LocalizedText></strong><Sparkline data={history.slice(-40)} field={metric.field}/></div>)}</div><small><LocalizedText id="latest_observation_sparklines_show_last_40_oos_observations_8d9027"/></small></div></aside>
      </section>
      {errors.length > 0 && <div className="api-notice" role="status"><LocalizedText>{errors.join(', ')}</LocalizedText><LocalizedText id="unavailable_9cd983" before after/><button onClick={() => setRefresh(value => value + 1)} disabled={loading}><LocalizedText>{loading ? 'Retrying…' : 'Retry connection'}</LocalizedText></button></div>}
      <section className="market-grid" aria-label={t("Market overview")}>
        <article className={`market-card us-card tone-${tone}`}><div className="city-image us-image"/><div className="market-card-content"><div className="card-heading"><h2><span className="flag">🇺🇸</span><LocalizedText id="u_s_market_9b3642" before/><ChevronRight size={18}/></h2><span className={`risk-badge ${tone}`}><LocalizedText>{level === '--' ? 'UNAVAILABLE' : `${level} RISK`}</LocalizedText></span></div><div className="us-card-body"><div className="score-block"><span className="score-label"><LocalizedText id="10_day_risk_score_f5fce8"/></span><div className={`risk-number ${tone}`}><LocalizedText>{format(score, 1)}</LocalizedText><small>/ 100</small></div><p><LocalizedText id="forward_looking_market_06aca8"/><br/><LocalizedText id="stress_warning_3eea66"/></p><div className="current-msi"><LocalizedText id="current_stress_msi_2ac8c2" after/><strong><LocalizedText>{format(modelAvailable(latest) ? latest?.market_stress_index : null, 3)}</LocalizedText></strong></div></div><div className="us-metrics"><div className="eyebrow"><LocalizedText id="market_snapshot_745f02"/></div>{metrics.map(metric => <div key={metric.label}><span><LocalizedText>{metric.label === 'Baa–Treasury' ? 'Credit Spread' : metric.label}</LocalizedText></span><strong><LocalizedText>{metric.value}</LocalizedText></strong></div>)}<Link href="/us" className="market-button"><LocalizedText id="explore_u_s_market_70ffd9"/><ArrowRight size={17}/></Link></div></div><div className="score-footnote"><LocalizedText id="low_30_d9463e" after/><span><LocalizedText id="watch_30_50_23abd9"/></span><span><LocalizedText id="elevated_50_70_ee49cd"/></span><span><LocalizedText id="high_70_b19f6d"/></span></div></div></article>
        <article className={`market-card korea-card tone-${koreaTone}`} id="korea">
          <div className="city-image korea-image"/>
          <div className="market-card-content">
            <div className="card-heading">
              <h2>
                <span className="flag">🇰🇷</span><LocalizedText id="korea_market_beaf00" before after/><ChevronRight size={18}/>
              </h2>
              <span className={`risk-badge ${koreaTone}`}>
                <LocalizedText>{koreaStatus}</LocalizedText>
              </span>
            </div>

            <div className="korea-body">
              <span className="eyebrow"><LocalizedText id="10_day_market_stress_risk_05a549"/></span>
              <div className={`risk-number ${koreaTone}`}>
                <LocalizedText>{format(koreaScore, 1)}</LocalizedText>
                <small>/ 100</small>
              </div>
              <p><LocalizedText id="forward_looking_korean_5264a6" before/><br/><LocalizedText id="market_stress_warning_47172f" before after/></p>
              <div className="current-msi"><LocalizedText id="current_stress_msi_2ac8c2" before/><LocalizedText>{' '}</LocalizedText>
                <strong><LocalizedText>{format(modelAvailable(koreaLatest) ? koreaLatest?.market_stress_index : null, 3)}</LocalizedText></strong>
              </div>
            </div>

            <div className="korea-preview">
              <span><LocalizedText id="kospi_200_931c45" before after/><small><LocalizedText>{format(koreaLatest?.kospi200, 2)}</LocalizedText></small>
              </span>

              <span><LocalizedText id="vkospi_94fdc0" before after/><small><LocalizedText>{format(koreaLatest?.vkospi, 2)}</LocalizedText></small>
              </span>

              <span><LocalizedText id="credit_8a45d3" before after/><small>
                  <LocalizedText>{finite(koreaLatest?.korea_credit_spread_bp)
                    ? `${koreaLatest.korea_credit_spread_bp.toFixed(1)} bp`
                    : '--'}</LocalizedText>
                </small>
              </span>

              <Link href="/korea" className="market-button"><LocalizedText id="explore_korea_market_c2ece9" before after/><ArrowRight size={17}/>
              </Link>
            </div>
          </div>
        </article>
      </section>
      <CrossMarketSnapshot us={latest} korea={koreaLatest}/>
      <section className="drivers-panel"><div className="drivers-title"><h2><LocalizedText id="current_risk_drivers_ee132f"/></h2><p><LocalizedText id="leading_shap_contributions_781cf1"/><LocalizedText>{shap?.date ? ` · ${shap.date}` : ''}</LocalizedText></p></div><div className="driver-groups">{groups.map(group => {
        const drivers = shap?.top_drivers.filter(driver => group.match(driver.feature) && finite(driver.shap_value)) ?? [];
        const net = drivers.reduce((sum, driver) => sum + driver.shap_value, 0);
        const color = !drivers.length || net === 0 ? 'muted' : net > 0 ? 'red' : 'green';
        const Icon = group.icon;
        return <div className={`driver channel-${color}`} key={group.label}><span className="driver-icon"><Icon size={20}/></span><div><span><LocalizedText>{group.label}</LocalizedText></span><strong className={color}>{!drivers.length ? '--' : net === 0 ? <LocalizedText>{'→ Neutral'}</LocalizedText> : <>{net > 0 ? <ArrowUp size={13}/> : <ArrowDown size={13}/>}<LocalizedText id="net_risk_73ac73"/><LocalizedText>{net > 0 ? 'Increasing' : 'Reducing'}</LocalizedText></>}</strong></div></div>;
      })}</div><small><LocalizedText id="net_effect_of_leading_factors_on_model_output_not_probability_cha_5d681b"/></small></section>
      <section className="history-grid">
        <article className="history-panel"><div className="chart-heading"><div><h2><span className="blue-dot"/><LocalizedText id="historical_market_stress_88bd29"/></h2><p><LocalizedText id="u_s_xgboost_10_day_risk_score_vs_spy_04c60c"/></p></div><div className="range-buttons" aria-label={t("Historical chart time range")}>{(['1Y', '3Y', '5Y', 'ALL'] as Range[]).map(value => <button key={value} onClick={() => setRange(value)} aria-pressed={range === value} className={range === value ? 'selected' : ''}><LocalizedText>{value}</LocalizedText></button>)}</div></div><div className="chart-legend"><span><i/><LocalizedText id="10_day_risk_score_left_axis_100_2e8496"/></span><span><i/><LocalizedText id="spy_right_axis_usd_414bb2"/></span></div><div className="history-chart">{filtered.length ? <ResponsiveContainer width="100%" height="100%"><ComposedChart data={filtered} margin={{ top: 12, right: 0, bottom: 0, left: -18 }}><defs><linearGradient id="home-risk-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#1dd6b0" stopOpacity={.3}/><stop offset="100%" stopColor="#1dd6b0" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#1a2a37" vertical={false}/><XAxis dataKey="date" tickFormatter={date => date.slice(0, 4)} minTickGap={55} tick={{ fill: '#7890a4', fontSize: 12 }} axisLine={false} tickLine={false}/><YAxis yAxisId="risk" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fill: '#7890a4', fontSize: 12 }} axisLine={false} tickLine={false}/><YAxis yAxisId="spy" orientation="right" domain={['auto', 'auto']} tick={{ fill: '#7890a4', fontSize: 12 }} axisLine={false} tickLine={false}/><Tooltip contentStyle={{ background: '#0b1a27f2', border: '1px solid #3c5b70', borderRadius: 10, color: '#e4eef6', boxShadow: '0 12px 32px #0008', padding: '12px 16px', fontSize: 12, backdropFilter: 'blur(12px)' }} formatter={(value: number, name: string) => [finite(value) ? value.toFixed(name === 'SPY' ? 2 : 1) : '--', t(name === 'SPY' ? 'SPY (USD)' : '10-Day Risk Score / 100')]}/><Area yAxisId="risk" type="linear" dataKey="risk_score_xgboost" name={t("10-Day Risk Score")} stroke="#47e1bf" strokeWidth={2.2} fill="url(#home-risk-gradient)" isAnimationActive={false}/><Line yAxisId="spy" type="linear" dataKey="spy" name={t("SPY")} stroke="#eab451" strokeWidth={1.7} dot={false} isAnimationActive={false}/></ComposedChart></ResponsiveContainer> : <div className="chart-empty"><BarChart3 size={30}/><span><LocalizedText>{loading ? 'Loading historical observations…' : 'Historical data unavailable'}</LocalizedText></span><small><LocalizedText id="real_walk_forward_out_of_sample_data_appears_here_34f7e9"/></small></div>}</div><div className="chart-note"><Database size={12}/><LocalizedText id="purged_walk_forward_oos_predictions_risk_score_is_not_calibrated__2966ed"/></div></article>
        <aside className="insights-panel" id="insights"><div className="insights-heading"><h2><LocalizedText id="key_insights_ffd557"/></h2><Lightbulb size={18}/></div><div className="insight"><span>01</span><div><h3><LocalizedText id="a_warning_not_a_price_forecast_740268"/></h3><p><LocalizedText id="the_model_assesses_broad_u_s_financial_market_stress_over_the_nex_065f9f"/></p></div></div><div className="insight"><span>02</span><div><h3><LocalizedText id="two_distinct_perspectives_3ce1b8"/></h3><p><LocalizedText id="msi_measures_current_stress_the_risk_score_looks_ahead_071068"/></p></div></div><div className="insight"><span>03</span><div><h3><LocalizedText id="validation_comes_first_72f04f"/></h3><p><LocalizedText id="historical_scores_use_purged_walk_forward_out_of_sample_predictio_6de1a5"/></p></div></div><Link href="/validation"><LocalizedText id="explore_the_evidence_02a00d"/><ArrowRight size={15}/></Link></aside>
      </section>
      <section className="bottom-grid" aria-label={t("Explore the project")}><Link href="/validation" className="bottom-card"><span className="bottom-icon blue"><BarChart3/></span><div><h2><LocalizedText id="model_validation_78b3dc"/></h2><p><LocalizedText id="out_of_sample_performance_3c5a4a"/><br/><LocalizedText id="and_historical_event_analysis_a8754b"/></p></div><ChevronRight/></Link><Link href="/methodology" className="bottom-card"><span className="bottom-icon purple"><BookOpen/></span><div><h2><LocalizedText id="methodology_b509d9"/></h2><p><LocalizedText id="data_target_definition_cc2690"/><br/><LocalizedText id="and_modeling_approach_4f38db"/></p></div><ChevronRight/></Link><button className="bottom-card" onClick={() => setInsightsOpen(value => !value)} aria-expanded={insightsOpen} aria-controls="expanded-insights"><span className="bottom-icon gold"><Lightbulb/></span><div><h2><LocalizedText id="key_insights_ffd557"/></h2><p><LocalizedText id="understand_the_current_assessment_925210"/><br/><LocalizedText id="and_what_the_signals_mean_de21a0"/></p></div><ChevronRight/></button></section>
      {insightsOpen && <section id="expanded-insights" className="expanded-insights"><h2><LocalizedText id="understanding_the_assessment_5bbbb6"/></h2><p><LocalizedText>{finite(score) ? `The latest U.S. Risk Score is ${score.toFixed(1)} / 100 (${level}).` : 'The latest U.S. Risk Score is unavailable.'}</LocalizedText><LocalizedText id="the_score_assesses_broad_stress_events_not_stock_price_direction__7a47c9" before/></p><Link href="/methodology"><LocalizedText id="read_the_methodology_83c5b8" after/><ArrowRight size={14}/></Link></section>}
      <GlobalAssessment us={latest} korea={koreaLatest}/>
      <ModelDisclaimer/>
      <footer className="home-footer"><span><Globe2 size={13}/><LocalizedText id="market_risk_intelligence_b27728"/></span><span><LocalizedText id="u_s_korea_market_stress_early_warning_10_trading_days_xgboost_8e92b3"/></span></footer>
    </div>
  </div>;
}
