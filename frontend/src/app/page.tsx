'use client';
import { modelAvailable } from './components/market-data';
import MarketMonitorCard from './components/MarketMonitorCard';
import { HistoryChart } from './components/MarketDetail';
import type { HistoryPoint } from './components/market-data';
import { KoreaIndustryResearch } from './components/KoreaMonitor';

import { LocalizedText, useI18n } from './i18n/provider';


import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Activity, ArrowDown, ArrowRight, ArrowUp, BarChart3, BookOpen, ChevronRight, Database, Globe2, Lightbulb, RefreshCw } from 'lucide-react';
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import CrossMarketSnapshot, { GlobalAssessment, ModelDisclaimer } from './components/CrossMarketSnapshot';

const API_URL = '';
interface Latest { warning_active?: boolean; warning_threshold?: number | null; stress_threshold?: number | null; is_stress_event?: boolean; data_health?: import('./components/market-data').DataHealth; last_updated: string; risk_score_10d: number | null; spy_price: number | null; vix_level: number | null; baa_treasury_spread: number | null; market_stress_index: number | null }

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

interface Historical extends HistoryPoint { msi: number | null; date: string; spy: number | null; vix: number | null; baa_treasury_spread: number | null; risk_score_xgboost: number | null }
interface Shap { date: string; top_drivers: { feature: string; shap_value: number }[] }
type Range = '1Y' | '3Y' | '5Y' | 'ALL';
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

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
  const [chartView, setChartView] = useState<'risk' | 'msi'>('risk');
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
  const filtered = useMemo(() => {
    if (range === 'ALL' || !history.length) return history;
    const start = new Date(history[history.length - 1].date);
    start.setFullYear(start.getFullYear() - Number(range[0]));
    return history.filter(point => new Date(point.date) >= start);
  }, [history, range]);
  const groups = [
    { label: 'Stock Market', icon: BarChart3, match: (f: string) => f.startsWith('SPY_') },
    { label: 'Market Volatility', icon: Activity, match: (f: string) => f.startsWith('VIX_') },
    { label: 'Credit Conditions', icon: Database, match: (f: string) => /^(Credit_|BAA_)/.test(f) },
  ];
  return <div className="risk-home overview-console">
    <div className="home-content">
      <header className="overview-console-header"><div><div className="eyebrow"><LocalizedText>{'U.S. / KOREA · PRODUCTION V1'}</LocalizedText></div><h1><LocalizedText>{'MARKET STRESS EARLY WARNING SYSTEM'}</LocalizedText></h1><p><LocalizedText>{'Future risk. Observed stress. Dated evidence.'}</LocalizedText></p></div><div className="overview-header-actions"><button className="market-button" onClick={()=>setRefresh(value=>value+1)} disabled={loading}><RefreshCw size={14}/><LocalizedText>{'Refresh snapshots'}</LocalizedText></button><Link href="/compare" className="market-button"><LocalizedText>{'Compare markets'}</LocalizedText><ArrowRight size={15}/></Link></div></header>
      {errors.filter(error=>error!=='SHAP drivers').length > 0 && <div className="api-notice" role="status"><LocalizedText>{errors.filter(error=>error!=='SHAP drivers').join(', ')}</LocalizedText><LocalizedText id="unavailable_9cd983" before after/><button onClick={() => setRefresh(value => value + 1)} disabled={loading}><LocalizedText>{loading ? 'Retrying…' : 'Retry connection'}</LocalizedText></button></div>}
      <section className="market-grid" aria-label={t("Market overview")}><MarketMonitorCard market="us" latest={latest}/><MarketMonitorCard market="korea" latest={koreaLatest}/></section>
      <section className="overview-evidence-strip"><span><Database size={15}/><LocalizedText>{'Live snapshots and archived evidence are separate'}</LocalizedText></span><span><LocalizedText>{'Each market retains its own observation date and event definition.'}</LocalizedText></span><Link href="/methodology"><LocalizedText>{'Review methodology'}</LocalizedText><ArrowRight size={13}/></Link></section>
      <KoreaIndustryResearch/>
      <details className="console-disclosure"><summary><LocalizedText>{'Cross-market snapshot / source details'}</LocalizedText></summary><CrossMarketSnapshot us={latest} korea={koreaLatest}/></details>
      {shap?.top_drivers.some(driver=>finite(driver.shap_value)) ? <details className="console-disclosure"><summary><LocalizedText>{'SHAP / model explanation'}</LocalizedText> · {shap.date}</summary>
      <section className="drivers-panel"><div className="drivers-title"><h2><LocalizedText id="current_risk_drivers_ee132f"/></h2><p><LocalizedText id="leading_shap_contributions_781cf1"/><LocalizedText>{shap?.date ? ` · ${shap.date}` : ''}</LocalizedText></p></div><div className="driver-groups">{groups.map(group => {
        const drivers = shap?.top_drivers.filter(driver => group.match(driver.feature) && finite(driver.shap_value)) ?? [];
        const net = drivers.reduce((sum, driver) => sum + driver.shap_value, 0);
        const color = !drivers.length || net === 0 ? 'muted' : net > 0 ? 'red' : 'green';
        const Icon = group.icon;
        return <div className={`driver channel-${color}`} key={group.label}><span className="driver-icon"><Icon size={20}/></span><div><span><LocalizedText>{group.label}</LocalizedText></span><strong className={color}>{!drivers.length ? '--' : net === 0 ? <LocalizedText>{'→ Neutral'}</LocalizedText> : <>{net > 0 ? <ArrowUp size={13}/> : <ArrowDown size={13}/>}<LocalizedText id="net_risk_73ac73"/><LocalizedText>{net > 0 ? 'Increasing' : 'Reducing'}</LocalizedText></>}</strong></div></div>;
      })}</div><small><LocalizedText id="net_effect_of_leading_factors_on_model_output_not_probability_cha_5d681b"/></small></section>
      </details> : <div className="overview-explainability-note"><LocalizedText>{'Valid SHAP attribution is unavailable for this snapshot.'}</LocalizedText></div>}
      <section className="history-grid">
        <article className="history-panel"><div className="chart-heading"><div><h2><span className="blue-dot"/><LocalizedText>{'HISTORICAL OOS / BACKTEST'}</LocalizedText></h2><p><LocalizedText id="u_s_xgboost_10_day_risk_score_vs_spy_04c60c"/></p></div><div className="range-buttons" aria-label={t("Historical chart time range")}>{(['1Y', '3Y', '5Y', 'ALL'] as Range[]).map(value => <button key={value} onClick={() => setRange(value)} aria-pressed={range === value} className={range === value ? 'selected' : ''}><LocalizedText>{value}</LocalizedText></button>)}</div></div><div className="range-buttons overview-chart-tabs" aria-label={t('Historical evidence view')}><button onClick={()=>setChartView('risk')} aria-pressed={chartView==='risk'} className={chartView==='risk'?'selected':''}><LocalizedText>{'OOS Risk Score / SPY'}</LocalizedText></button><button onClick={()=>setChartView('msi')} aria-pressed={chartView==='msi'} className={chartView==='msi'?'selected':''}><LocalizedText>{'Observed MSI archive'}</LocalizedText></button></div>{chartView==='risk' && <div className="chart-legend"><span><i/><LocalizedText id="10_day_risk_score_left_axis_100_2e8496"/></span><span><i/><LocalizedText id="spy_right_axis_usd_414bb2"/></span></div>}<div className="history-chart">{chartView==='msi' ? <HistoryChart data={filtered} fields={[{key:'msi',label:'Archived observed MSI',color:'#7ebbd6'}]}/> : filtered.length ? <ResponsiveContainer width="100%" height="100%"><ComposedChart data={filtered} margin={{ top: 12, right: 0, bottom: 0, left: -18 }}><defs><linearGradient id="home-risk-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#1dd6b0" stopOpacity={.3}/><stop offset="100%" stopColor="#1dd6b0" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#1a2a37" vertical={false}/><XAxis dataKey="date" tickFormatter={date => date.slice(0, 4)} minTickGap={55} tick={{ fill: '#7890a4', fontSize: 12 }} axisLine={false} tickLine={false}/><YAxis yAxisId="risk" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fill: '#7890a4', fontSize: 12 }} axisLine={false} tickLine={false}/><YAxis yAxisId="spy" orientation="right" domain={['auto', 'auto']} tick={{ fill: '#7890a4', fontSize: 12 }} axisLine={false} tickLine={false}/><Tooltip contentStyle={{ background: '#0b1a27f2', border: '1px solid #3c5b70', borderRadius: 10, color: '#e4eef6', boxShadow: '0 12px 32px #0008', padding: '12px 16px', fontSize: 12, backdropFilter: 'blur(12px)' }} formatter={(value: number, name: string) => [finite(value) ? value.toFixed(name === 'SPY' ? 2 : 1) : '--', t(name === 'SPY' ? 'SPY (USD)' : '10-Day Risk Score / 100')]}/><Area yAxisId="risk" type="linear" dataKey="risk_score_xgboost" name={t("10-Day Risk Score")} stroke="#47e1bf" strokeWidth={2.2} fill="url(#home-risk-gradient)" isAnimationActive={false}/><Line yAxisId="spy" type="linear" dataKey="spy" name={t("SPY")} stroke="#eab451" strokeWidth={1.7} dot={false} isAnimationActive={false}/></ComposedChart></ResponsiveContainer> : <div className="chart-empty"><BarChart3 size={30}/><span><LocalizedText>{loading ? 'Loading historical observations…' : 'Historical data unavailable'}</LocalizedText></span><small><LocalizedText id="real_walk_forward_out_of_sample_data_appears_here_34f7e9"/></small></div>}</div><p className="monitor-caption">{filtered.length ? `${filtered[0].date} — ${filtered[filtered.length-1].date}` : '—'} · <LocalizedText>{'Historical observations, not live forecast history.'}</LocalizedText></p><div className="chart-note"><Database size={12}/><LocalizedText id="purged_walk_forward_oos_predictions_risk_score_is_not_calibrated__2966ed"/></div></article>
        <aside className="insights-panel" id="insights"><div className="insights-heading"><h2><LocalizedText id="key_insights_ffd557"/></h2><Lightbulb size={18}/></div><div className="insight"><span>01</span><div><h3><LocalizedText id="a_warning_not_a_price_forecast_740268"/></h3><p><LocalizedText id="the_model_assesses_broad_u_s_financial_market_stress_over_the_nex_065f9f"/></p></div></div><div className="insight"><span>02</span><div><h3><LocalizedText id="two_distinct_perspectives_3ce1b8"/></h3><p><LocalizedText id="msi_measures_current_stress_the_risk_score_looks_ahead_071068"/></p></div></div><div className="insight"><span>03</span><div><h3><LocalizedText id="validation_comes_first_72f04f"/></h3><p><LocalizedText id="historical_scores_use_purged_walk_forward_out_of_sample_predictio_6de1a5"/></p></div></div><Link href="/validation"><LocalizedText id="explore_the_evidence_02a00d"/><ArrowRight size={15}/></Link></aside>
      </section>
      <section className="bottom-grid" aria-label={t("Explore the project")}><Link href="/validation" className="bottom-card"><span className="bottom-icon blue"><BarChart3/></span><div><h2><LocalizedText id="model_validation_78b3dc"/></h2><p><LocalizedText id="out_of_sample_performance_3c5a4a"/><br/><LocalizedText id="and_historical_event_analysis_a8754b"/></p></div><ChevronRight/></Link><Link href="/methodology" className="bottom-card"><span className="bottom-icon purple"><BookOpen/></span><div><h2><LocalizedText id="methodology_b509d9"/></h2><p><LocalizedText id="data_target_definition_cc2690"/><br/><LocalizedText id="and_modeling_approach_4f38db"/></p></div><ChevronRight/></Link><button className="bottom-card" onClick={() => setInsightsOpen(value => !value)} aria-expanded={insightsOpen} aria-controls="expanded-insights"><span className="bottom-icon gold"><Lightbulb/></span><div><h2><LocalizedText id="key_insights_ffd557"/></h2><p><LocalizedText id="understand_the_current_assessment_925210"/><br/><LocalizedText id="and_what_the_signals_mean_de21a0"/></p></div><ChevronRight/></button></section>
      {insightsOpen && <section id="expanded-insights" className="expanded-insights"><h2><LocalizedText id="understanding_the_assessment_5bbbb6"/></h2><p><LocalizedText>{finite(score) ? `The latest U.S. Risk Score is ${score.toFixed(1)} / 100 (${level}).` : 'The latest U.S. Risk Score is unavailable.'}</LocalizedText><LocalizedText id="the_score_assesses_broad_stress_events_not_stock_price_direction__7a47c9" before/></p><Link href="/methodology"><LocalizedText id="read_the_methodology_83c5b8" after/><ArrowRight size={14}/></Link></section>}
      <details className="console-disclosure"><summary><LocalizedText>{'Cross-market interpretation'}</LocalizedText></summary><GlobalAssessment us={latest} korea={koreaLatest}/></details>
      <ModelDisclaimer/>
      <footer className="home-footer"><span><Globe2 size={13}/><LocalizedText id="market_risk_intelligence_b27728"/></span><span><LocalizedText id="u_s_korea_market_stress_early_warning_10_trading_days_xgboost_8e92b3"/></span></footer>
    </div>
  </div>;
}
