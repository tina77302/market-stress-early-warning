'use client';

import { Activity, ShieldAlert, Layers, Network, Database, TrendingUp } from 'lucide-react';
import { LocalizedText, useI18n } from '../i18n/provider';
import { finite, fmt, HistoryPoint, Latest, modelAvailable } from './market-data';

function usedDate(latest: Latest | null, series: string) {
  const input = latest?.input_series?.find(item => item.series === series);
  return input?.used_observation_date || input?.observation_date || latest?.last_updated || '—';
}

export function KoreaMonitorHero({ latest, status }: { latest: Latest | null; status: string }) {
  const { t } = useI18n();
  const available = modelAvailable(latest);
  const score = available ? latest!.risk_score_10d! : null;
  const msi = available ? latest!.market_stress_index! : null;
  const threshold = latest?.stress_threshold;
  const sourceValue = (series: string) => latest?.input_series?.find(item => item.series === series)?.value;
  const metrics = [
    { label: 'KOSPI200', value: fmt(latest?.kospi200), date: usedDate(latest, 'KOSPI200') },
    { label: 'VKOSPI', value: fmt(latest?.vkospi), date: usedDate(latest, 'VKOSPI') },
    { label: 'Credit Spread', value: fmt(latest?.korea_credit_spread_bp, 1, ' bp'), date: `${usedDate(latest, 'Korea_Treasury_3Y')} / ${usedDate(latest, 'Korea_Corporate_AAminus_3Y')}` },
    { label: 'Treasury 3Y', value: fmt(sourceValue('Korea_Treasury_3Y'), 3, '%'), date: usedDate(latest, 'Korea_Treasury_3Y') },
    { label: 'Corporate AA− 3Y', value: fmt(sourceValue('Korea_Corporate_AAminus_3Y'), 3, '%'), date: usedDate(latest, 'Korea_Corporate_AAminus_3Y') },
  ];
  return <section className="monitor-hero" aria-label={t('Market status')}>
    <article className={`monitor-panel monitor-risk ${status === 'WARNING' ? 'monitor-warning' : ''}`}>
      <header className="monitor-panel-title"><ShieldAlert size={22}/><div><h2><LocalizedText>{'10-trading-day forward model Risk Score'}</LocalizedText></h2><span><LocalizedText>{'FUTURE RISK · PRODUCTION V1'}</LocalizedText></span></div></header>
      <div className="monitor-risk-body">
        <div className="monitor-dial">
          <svg viewBox="0 0 310 205" role="img" aria-label={t(`Risk Score ${fmt(score, 1)} / 100; warning threshold 50`)}>
            <defs><linearGradient id="korea-risk-arc" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#c39a55"/><stop offset="1" stopColor="#e5b465"/></linearGradient></defs>
            <path d="M 30 160 A 125 125 0 0 1 280 160" fill="none" stroke="#21394b" strokeWidth="15" pathLength="100"/>
            {finite(score) && <path d="M 30 160 A 125 125 0 0 1 280 160" fill="none" stroke={status === 'WARNING' ? '#db727a' : 'url(#korea-risk-arc)'} strokeWidth="15" pathLength="100" strokeDasharray={`${score} 100`}/>}
            <path d="M 155 24 V 48" stroke="#e5b465" strokeWidth="2" strokeDasharray="3 3"/>
            <text x="155" y="17" textAnchor="middle" fill="#e5c38c" fontSize="12">50</text>
            <text x="24" y="186" fill="#8ca9be" fontSize="11">0</text><text x="276" y="186" fill="#8ca9be" fontSize="11">100</text>
          </svg>
          <div className="monitor-dial-value"><strong>{fmt(score, 1)}</strong><span>/ 100</span></div>
          <small><LocalizedText>{'Model score · not a probability'}</LocalizedText></small>
        </div>
        <div className="monitor-warning-state"><span className="monitor-label"><LocalizedText>{'V1 operational warning'}</LocalizedText></span><strong className={status === 'WARNING' ? 'red' : ''}><LocalizedText>{status === 'BELOW WARNING' ? 'Operational warning not triggered' : status}</LocalizedText></strong><span className="monitor-threshold"><LocalizedText>{'Warning ≥ 50'}</LocalizedText></span><p><LocalizedText>{'Being below the warning threshold does not rule out market shocks.'}</LocalizedText></p></div>
      </div>
      <footer><LocalizedText>{'Data date'}</LocalizedText>: {latest?.last_updated || '—'}</footer>
    </article>
    <article className={`monitor-panel monitor-msi ${latest?.is_stress_event ? 'monitor-warning' : ''}`}>
      <header className="monitor-panel-title"><Activity size={22}/><div><h2><LocalizedText>{'Current Stress'}</LocalizedText></h2><span><LocalizedText>{'OBSERVED MARKET STRESS · MSI'}</LocalizedText></span></div></header>
      <div className="monitor-msi-value">{fmt(msi, 3)}<small><LocalizedText>{'MSI'}</LocalizedText></small></div>
      {finite(threshold) && threshold > 0 && finite(msi) ? <>
        <p className="monitor-msi-reference"><LocalizedText>{'Stress Event threshold'}</LocalizedText> <strong>{fmt(threshold, 3)}</strong></p>
        <div className="metric-gauge" role="img" aria-label={t(`MSI ${fmt(msi, 3)}; stress threshold ${fmt(threshold, 3)}`)}><span className="gauge-fill" style={{width:`${Math.min(100, Math.max(0, msi / (threshold * 2) * 100))}%`}}/><i className="gauge-threshold" style={{left:'50%'}}/></div>
        <div className="gauge-labels"><span>0</span><span>{fmt(threshold, 3)}</span><span>{fmt(threshold * 2, 3)}</span></div>
      </> : <p><LocalizedText>{'Stress reference unavailable'}</LocalizedText></p>}
      <div className="monitor-msi-state"><span className="status-dot"/><LocalizedText>{typeof latest?.is_stress_event === 'boolean' ? latest.is_stress_event ? 'STRESS EVENT' : 'Stress Event threshold not reached' : 'UNAVAILABLE'}</LocalizedText></div>
      <p className="monitor-caption"><LocalizedText>{'Below the Stress Event threshold does not mean low market stress.'}</LocalizedText></p>
      <footer><LocalizedText>{'Data date'}</LocalizedText>: {latest?.last_updated || '—'}</footer>
    </article>
    <article className="monitor-panel monitor-key-inputs"><header className="monitor-panel-title"><Database size={19}/><h2><LocalizedText>{'Key market inputs'}</LocalizedText></h2></header><div>{metrics.map(metric=><div className="monitor-input" key={metric.label}><span><LocalizedText>{metric.label}</LocalizedText><small>{metric.date}</small></span><strong>{metric.value}</strong></div>)}</div><footer><LocalizedText>{'Credit dates: Treasury / Corporate'}</LocalizedText></footer></article>
  </section>;
}

function ArchiveSparkline({ data, field }: { data: HistoryPoint[]; field: string }) {
  const values = data.map(row => row[field]);
  const present = values.filter(finite);
  if (present.length < 2) return null;
  const min = Math.min(...present), span = Math.max(...present) - min || 1;
  // Preserve missing observations as gaps; no invented interpolation.
  const points = values.map((value,index) => finite(value) ? `${index === 0 || !finite(values[index-1]) ? 'M' : 'L'}${index / (values.length-1)*140},${32-(value-min)/span*27}` : '').join(' ');
  return <svg className="monitor-sparkline" viewBox="0 0 140 36" aria-hidden="true"><path d={points} fill="none" stroke="currentColor" strokeWidth="1.6"/></svg>;
}

export function KoreaSignals({ latest, archive }: { latest: Latest | null; archive: HistoryPoint[] }) {
  const channels = [
    { label: 'Equity', field: 'kospi200', value: fmt(latest?.kospi200), icon: TrendingUp },
    { label: 'Volatility', field: 'vkospi', value: fmt(latest?.vkospi), icon: Activity },
    { label: 'Credit', field: 'korea_credit_spread_bp', value: fmt(latest?.korea_credit_spread_bp, 1, ' bp'), icon: Database },
  ];
  return <section className="monitor-panel monitor-signals"><header className="monitor-row-heading"><h2><LocalizedText>{'Early Warning Signals'}</LocalizedText></h2><span><LocalizedText>{'Observed model inputs · not independent alerts'}</LocalizedText></span></header><div className="monitor-signal-grid">{channels.map(({label,field,value,icon:Icon})=><article key={label}><div className="monitor-signal-title"><Icon size={20}/><h3><LocalizedText>{label}</LocalizedText></h3><strong>{value}</strong></div><div className="monitor-signal-bottom"><span><LocalizedText>{'Observed input'}</LocalizedText> · {latest?.last_updated || '—'}</span><ArchiveSparkline data={archive} field={field}/></div></article>)}<article className="monitor-research-signal"><div className="monitor-signal-title"><Layers size={20}/><h3><LocalizedText>{'Industry Stress'}</LocalizedText></h3></div><span className="research-chip"><LocalizedText>{'RESEARCH / SHADOW'}</LocalizedText></span><small><LocalizedText>{'Live industry feed unavailable'}</LocalizedText></small></article></div><p className="monitor-caption"><LocalizedText>{'Sparklines: archived observations only, not current-day trends.'}</LocalizedText> {archive.length ? `${archive[0].date} — ${archive[archive.length-1].date}` : '—'}</p></section>;
}

export function KoreaIndustryResearch() {
  return <aside className="research-status-panel monitor-industry-research"><div className="monitor-research-header"><span className="research-chip"><LocalizedText>{'Research analysis / not a live operational indicator'}</LocalizedText></span><h2><LocalizedText>{'Industry Stress'}</LocalizedText></h2></div><div className="monitor-research-pair"><div><Layers size={22}/><h3><LocalizedText>{'Industry stress heatmap'}</LocalizedText></h3><p><LocalizedText>{'No validated live industry matrix is available.'}</LocalizedText></p></div><div><Network size={22}/><h3><LocalizedText>{'Industry diffusion'}</LocalizedText></h3><p><LocalizedText>{'Breadth and concentration remain research context; no live counts or rankings.'}</LocalizedText></p></div></div></aside>;
}

export function KoreaArchiveTimeline({ data, currentDate }: { data: HistoryPoint[]; currentDate?: string }) {
  const rows = data.slice(-7);
  const fields = [{key:'risk_score_xgboost',label:'OOS Risk Score'},{key:'msi',label:'MSI'},{key:'kospi200',label:'KOSPI200'},{key:'vkospi',label:'VKOSPI'},{key:'korea_credit_spread_bp',label:'Credit spread (bp)'}];
  return <section className="monitor-panel monitor-timeline"><header className="monitor-row-heading"><h2><LocalizedText>{'Dated stress timeline'}</LocalizedText></h2><span className="archive-badge"><LocalizedText>{'HISTORICAL OOS / BACKTEST'}</LocalizedText></span></header>{rows.length ? <div className="monitor-table-scroll"><table><thead><tr><th><LocalizedText>{'Observation date'}</LocalizedText></th>{rows.map(row=><th key={row.date}>{row.date}</th>)}</tr></thead><tbody>{fields.map(field=><tr key={field.key}><th scope="row"><LocalizedText>{field.label}</LocalizedText></th>{rows.map(row=><td key={row.date}>{fmt(row[field.key],field.key==='msi'?3:field.key==='risk_score_xgboost'||field.key==='korea_credit_spread_bp'?1:2)}</td>)}</tr>)}</tbody></table></div> : <p className="monitor-caption"><LocalizedText>{'No archived MSI observations available.'}</LocalizedText></p>}<p className="monitor-caption"><LocalizedText>{'Historical observations, not live forecast history.'}</LocalizedText> <LocalizedText>{'Current snapshot date'}</LocalizedText>: {currentDate || '—'}. <LocalizedText>{'Operational warning transitions are not supplied by this API.'}</LocalizedText></p></section>;
}
