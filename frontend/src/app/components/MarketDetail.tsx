'use client';

import { LocalizedText, useI18n } from '../i18n/provider';


import { useMemo, useState } from 'react';
import Link from 'next/link';
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { finite, modelAvailable, fmt, HistoryPoint, Market, signal, tone, useMarket } from './market-data';
import DataHealthNotice from './DataHealthNotice';
import { ModelDisclaimer } from './CrossMarketSnapshot';

export function HistoryChart({ data, fields, sharedScale = false }: { data: HistoryPoint[]; sharedScale?: boolean; fields: { key: string; label: string; color: string }[] }) {
  const { t, locale } = useI18n();

  if (!data.some(row => fields.some(field => finite(row[field.key])))) return <div className="chart-empty"><LocalizedText id="historical_data_unavailable_for_these_indicators_ee1177"/></div>;
  return <ResponsiveContainer width="100%" height="100%"><ComposedChart data={data}><CartesianGrid stroke="#203445" vertical={false}/><XAxis dataKey="date" minTickGap={55} tick={{ fill: '#8ba2b7', fontSize: 12 }}/>{fields.filter((_, i) => !sharedScale || i === 0).map((field, i) => <YAxis key={field.key} yAxisId={i} orientation={i === 1 ? 'right' : 'left'} domain={field.key === 'risk_score_xgboost' ? [0, 100] : ['auto', 'auto']} tick={{ fill: field.color, fontSize: 12 }}/>) }<Tooltip contentStyle={{ background: '#0b1a27', border: '1px solid #3c5b70', borderRadius: 10 }} formatter={(value: number) => fmt(value, 3)}/>{fields.map((field, i) => <Line key={field.key} yAxisId={sharedScale ? 0 : i} dataKey={field.key} name={t(String(field.label))} stroke={field.color} dot={false} strokeWidth={1.7} isAnimationActive={false}/>)}</ComposedChart></ResponsiveContainer>;
}
export default function MarketDetail({ market }: { market: Market }) {
  const { t, locale } = useI18n();

  const { latest, history, shap, loading, errors, retry } = useMarket(market);
  const [range, setRange] = useState<'1Y' | '3Y' | '5Y' | 'ALL'>('3Y');
  const korea = market === 'korea';
  const name = korea ? 'KOREA' : 'U.S.';
  const status = signal(market, latest);
  const drivers = shap?.top_drivers ?? [];
  const groups = [
    { label: 'Equity', match: (feature: string) => feature.startsWith(korea ? 'KOSPI200_' : 'SPY_') },
    { label: 'Volatility', match: (feature: string) => feature.startsWith(korea ? 'VKOSPI_' : 'VIX_') },
    { label: 'Credit', match: (feature: string) => /^(Credit_|BAA_)/.test(feature) },
  ].map(group => {
    const entries = drivers.filter(driver => group.match(driver.feature));
    const net = entries.reduce((sum, driver) => sum + driver.shap_value, 0);
    const representative = entries.reduce<typeof entries[number] | undefined>((largest, driver) => !largest || Math.abs(driver.shap_value) > Math.abs(largest.shap_value) ? driver : largest, undefined);
    return { label: group.label, representative, direction: !entries.length ? 'Unavailable' : net > 0 ? 'Net risk-increasing' : net < 0 ? 'Net risk-reducing' : 'Neutral', net, available: entries.length > 0 };
  });
  const filtered = useMemo(() => {
    if (range === 'ALL' || !history.length) return history;
    const start = new Date(history[history.length - 1].date);
    start.setFullYear(start.getFullYear() - Number(range[0]));
    return history.filter(row => new Date(row.date) >= start);
  }, [history, range]);
  const metrics = [
    [korea ? 'KOSPI200' : 'SPY', korea ? fmt(latest?.kospi200) : fmt(latest?.spy_price, 2, ' USD')],
    [korea ? 'VKOSPI' : 'VIX', fmt(korea ? latest?.vkospi : latest?.vix_level)],
    [korea ? 'AA− Corporate 3Y − Government 3Y' : 'Baa–Treasury', korea ? fmt(latest?.korea_credit_spread_bp, 1, ' bp') : fmt(latest?.baa_treasury_spread, 3, ' pp')],
  ];
  const charts = [
    { title: 'HISTORICAL 10-DAY OOS SCORE & EQUITY', note: 'Purged walk-forward out-of-sample scores · score / 100 on left axis; equity on right axis.', fields: [{ key: 'risk_score_xgboost', label: '10D Model Score / 100', color: '#47e1bf' }, { key: korea ? 'kospi200' : 'spy', label: korea ? 'KOSPI200' : 'SPY (USD)', color: '#eab451' }] },
    { title: 'MARKET STRESS INDEX', note: 'Current stress composite of equity, volatility and credit conditions.', fields: [{ key: 'msi', label: 'MSI', color: '#55c7ec' }] },
    { title: 'VOLATILITY & CREDIT CONDITIONS', note: korea ? 'VKOSPI on left axis · AA− Corporate − Government 3Y spread (bp) on right axis.' : 'VIX on left axis · Baa–Treasury spread (percentage points) on right axis.', fields: [{ key: korea ? 'vkospi' : 'vix', label: korea ? 'VKOSPI' : 'VIX', color: '#eab451' }, { key: korea ? 'korea_credit_spread_bp' : 'baa_treasury_spread', label: korea ? 'Credit spread (bp)' : 'Credit spread (pp)', color: '#b79cf3' }] },
  ];
  return <div className="risk-home detail-page"><div className="home-content">
    <section className="detail-heading"><div className="eyebrow"><LocalizedText>{name}</LocalizedText><LocalizedText id="market_intelligence_9509a7" before/></div><h1><LocalizedText id="10_day_financial_market_stress_outlook_d9d690"/></h1><p><LocalizedText id="independent_market_model_current_conditions_and_forward_looking_s_07fed9"/></p><div className="market-subnav"><Link href={korea ? '/korea/validation' : '/validation'}><LocalizedText>{name}</LocalizedText><LocalizedText id="validation_c27e35" before/></Link><Link href={korea ? '/korea/methodology' : '/methodology'}><LocalizedText>{name}</LocalizedText><LocalizedText id="methodology_964e6e" before/></Link></div></section>
    {loading && <div className="api-notice" role="status"><LocalizedText id="loading_8f26c6" after/><LocalizedText>{name}</LocalizedText><LocalizedText id="market_observations_6fb247" before/></div>}
    {!!errors.length && <div className="api-notice" role="status"><LocalizedText>{errors.join(', ')}</LocalizedText><LocalizedText id="unavailable_9cd983" before after/><button disabled={loading} onClick={retry}><LocalizedText id="retry_connection_a35123"/></button></div>}
    <DataHealthNotice market={market} latest={latest}/>
    <section className="detail-summary">
      <article className="history-panel"><div className="eyebrow"><LocalizedText>{korea ? 'KOREA 10D MODEL SCORE' : '10D RISK SCORE'}</LocalizedText></div><div className={`risk-number ${tone(status)}`}><LocalizedText>{fmt(modelAvailable(latest) ? latest?.risk_score_10d : null, 1)}</LocalizedText><small>/ 100</small></div><span className={`risk-badge ${tone(status)}`}><LocalizedText>{status}</LocalizedText></span><p className="comparison-note"><LocalizedText>{korea ? 'Fixed warning reference: 0.50 model score = 50 / 100.' : 'LOW <30 · WATCH 30–<50 · ELEVATED 50–<70 · HIGH ≥70'}</LocalizedText></p></article>
      <article className="history-panel"><div className="eyebrow"><LocalizedText>{name}</LocalizedText><LocalizedText id="market_stress_index_25c276" before/></div><div className="detail-msi"><LocalizedText>{fmt(modelAvailable(latest) ? latest?.market_stress_index : null, 3)}</LocalizedText></div><p><LocalizedText id="equal_weighted_equity_volatility_and_credit_stress_composite_ee065d"/></p>{korea && <p><LocalizedText id="stress_threshold_ec8621" after/><LocalizedText>{fmt(latest?.stress_threshold, 3)}</LocalizedText><br/><LocalizedText id="current_stress_event_60ff63" after/><LocalizedText>{typeof latest?.is_stress_event === 'boolean' ? latest.is_stress_event ? 'YES' : 'NO' : 'UNAVAILABLE'}</LocalizedText></p>}</article>
      <article className="history-panel"><div className="eyebrow"><LocalizedText id="deployment_model_8819af"/></div><h2 className="model-name"><LocalizedText id="xgboost_e63bae"/><LocalizedText>{ korea ? ' · Korea' : ' · U.S.'}</LocalizedText></h2><p><LocalizedText id="forecast_horizon_10_trading_days_02c9ae"/></p><p><LocalizedText id="validation_purged_walk_forward_oos_62fef6"/></p><p><LocalizedText id="last_observation_a4f8bb" after/><strong><LocalizedText>{latest?.last_updated || '—'}</LocalizedText></strong></p></article>
    </section>
    <section className="indicator-strip">{metrics.map(([label, value]) => <div key={label}><span><LocalizedText>{label}</LocalizedText></span><strong><LocalizedText>{value}</LocalizedText></strong></div>)}</section>
    <section className="history-panel assessment"><h2><LocalizedText id="current_market_assessment_0f2fdb"/></h2><p><LocalizedText>{modelAvailable(latest) && finite(latest?.risk_score_10d) ? `${name} is ${status} with a model score of ${fmt(latest.risk_score_10d, 1)} / 100. Current MSI is ${fmt(modelAvailable(latest) ? latest?.market_stress_index : null, 3)}.` : 'The latest model assessment is unavailable.'}</LocalizedText> <LocalizedText>{korea && modelAvailable(latest) && finite(latest?.risk_score_10d) ? `The displayed score is ${latest.risk_score_10d >= 50 ? 'at or above' : 'below'} the fixed 50 / 100 warning reference; the API warning state uses the unrounded model output.` : ''}</LocalizedText></p><p><LocalizedText>{groups.map(group => `${group.label}: ${group.direction.toLowerCase()}`).join(' · ')}</LocalizedText><LocalizedText id="effects_aggregate_only_the_leading_shap_factors_supplied_by_the_a_273c5a"/></p><p><LocalizedText>{drivers.length ? `Largest available contributions: ${[...drivers].sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value)).slice(0, 3).map(driver => `${driver.feature.replaceAll('_', ' ')} (${driver.shap_value > 0 ? '+' : ''}${fmt(driver.shap_value, 3)})`).join('; ')}.` : 'Major SHAP drivers are unavailable.'}</LocalizedText><LocalizedText id="these_contributions_explain_model_output_and_do_not_establish_cau_6e1864" before/></p></section>
    <section className="history-panel"><h2><LocalizedText id="current_risk_drivers_ee132f"/></h2><p className="comparison-note"><LocalizedText id="factor_summary_note"/></p><div className="driver-groups">{groups.map(group => <div className={`driver factor-summary channel-${!group.available ? 'muted' : group.net > 0 ? 'red' : group.net < 0 ? 'green' : 'muted'}`} key={group.label}><div><span><LocalizedText>{`${group.label} factors`}</LocalizedText></span><strong><LocalizedText>{!group.available ? 'Model contribution unavailable' : group.net > 0 ? 'Model risk contribution: Higher ↑' : group.net < 0 ? 'Model risk contribution: Lower ↓' : 'Model risk contribution: Neutral'}</LocalizedText></strong>{group.representative && <p className="factor-influence"><LocalizedText id="factor_main_influence" after/><LocalizedText>{group.representative.feature.replaceAll('_', ' ')}</LocalizedText></p>}</div></div>)}</div></section>
    <section className="history-panel"><div className="chart-heading"><h2><LocalizedText id="shap_model_drivers_65c699"/></h2><p><LocalizedText>{shap?.date || 'Date unavailable'}</LocalizedText> · <LocalizedText>{fmt(shap?.feature_count, 0)}</LocalizedText><LocalizedText id="features_4f9445" before/></p></div><div className="shap-grid">{[true, false].map(up => <div key={String(up)}><h3 className={up ? 'red' : 'green'}><LocalizedText id="risk_4138cc" after/><LocalizedText>{up ? 'INCREASING' : 'REDUCING'}</LocalizedText></h3>{drivers.filter(driver => up ? driver.shap_value > 0 : driver.shap_value < 0).length ? drivers.filter(driver => up ? driver.shap_value > 0 : driver.shap_value < 0).map(driver => <div className="shap-row" key={driver.feature}><span><LocalizedText>{driver.feature.replaceAll('_', ' ')}</LocalizedText></span><strong><LocalizedText>{fmt(driver.shap_value, 3)}</LocalizedText></strong></div>) : <p><LocalizedText>{`No ${up ? 'increasing' : 'reducing'} contributions available.`}</LocalizedText></p>}</div>)}</div><p className="comparison-note"><LocalizedText id="shap_values_represent_model_output_contributions_not_probability__277eba"/></p></section>
    <div className="chart-heading detail-range"><h2><LocalizedText id="historical_market_conditions_b8ef4d"/></h2><div className="range-buttons" aria-label={t("History range")}>{(['1Y', '3Y', '5Y', 'ALL'] as const).map(value => <button key={value} onClick={() => setRange(value)} aria-pressed={range === value} className={range === value ? 'selected' : ''}><LocalizedText>{value}</LocalizedText></button>)}</div></div>
    {charts.map(chart => <section className="history-panel" key={chart.title}><h2><LocalizedText>{chart.title}</LocalizedText></h2><p className="comparison-note"><LocalizedText>{chart.note}</LocalizedText></p><div className="history-chart"><HistoryChart data={filtered} fields={chart.fields}/></div></section>)}
    <ModelDisclaimer/>
  </div></div>;
}
