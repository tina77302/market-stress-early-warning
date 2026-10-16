'use client';

import Link from 'next/link';
import { ArrowUpRight, Activity, ShieldAlert } from 'lucide-react';
import { LocalizedText } from '../i18n/provider';
import DataHealthNotice from './DataHealthNotice';
import { finite, fmt, Latest, Market, modelAvailable, signal } from './market-data';

/** Presentation of existing classifications and API event states; no new alert rules. */
export default function MarketMonitorCard({market,latest}:{market:Market;latest:Latest|null}) {
  const korea=market==='korea';
  const available=modelAvailable(latest);
  const state=signal(market,latest);
  const warning=typeof latest?.warning_active==='boolean' ? latest.warning_active : null;
  const score=available?latest!.risk_score_10d:null;
  const msi=available?latest!.market_stress_index:null;
  const reference=latest?.warning_threshold;
  const stressReference=latest?.stress_threshold;
  const sourceDate=(series:string)=> { const source=latest?.input_series?.find(input=>input.series===series); return source?.used_observation_date||source?.observation_date||latest?.last_updated||'—'; };
  const metrics=korea ? [['KOSPI200',fmt(latest?.kospi200)],['VKOSPI',fmt(latest?.vkospi)],['Credit spread (bp)',fmt(latest?.korea_credit_spread_bp,1)]] : [['SPY',fmt(latest?.spy_price,2,' USD')],['VIX',fmt(latest?.vix_level)],['Credit spread (pp)',fmt(latest?.baa_treasury_spread,3)]];
  return <article className={`market-card ${korea?'korea-card':'us-card'} monitor-overview-card`}>
    <header className="monitor-overview-heading"><h2><span>{korea?'🇰🇷':'🇺🇸'}</span><LocalizedText>{korea?'Korea Market':'U.S. Market'}</LocalizedText></h2><Link href={korea?'/korea':'/us'}><LocalizedText>{'Open monitor'}</LocalizedText><ArrowUpRight size={15}/></Link></header>
    <DataHealthNotice market={market} latest={latest} compact/>
    <div className="overview-risk-stress">
      <div><div className="overview-metric-label"><ShieldAlert size={14}/><LocalizedText>{'Future Risk Score'}</LocalizedText></div><div className="overview-score">{fmt(score,1)}<small>/ 100</small></div><span className="overview-metric-caption"><LocalizedText>{'10-trading-day outlook · not a probability'}</LocalizedText></span><div className="metric-gauge"><span className="gauge-fill" style={{width:`${finite(score)?score:0}%`}}/>{finite(reference)&&<i className="gauge-threshold" style={{left:`${reference}%`}}/>}</div><p className="overview-reference"><LocalizedText>{'Operational threshold'}</LocalizedText>: {fmt(reference,0)} / 100</p></div>
      <div><div className="overview-metric-label"><Activity size={14}/><LocalizedText>{'Current Stress'}</LocalizedText></div><div className="overview-score overview-msi">{fmt(msi,3)}<small><LocalizedText>{'MSI'}</LocalizedText></small></div><span className="overview-metric-caption"><LocalizedText>{'Currently observed market conditions'}</LocalizedText></span>{finite(stressReference)&&stressReference>0&&finite(msi)&&<div className="metric-gauge"><span className="gauge-fill" style={{width:`${Math.min(100,Math.max(0,msi/(2*stressReference)*100))}%`}}/><i className="gauge-threshold" style={{left:'50%'}}/></div>}<p className="overview-reference"><LocalizedText>{'Stress Event threshold'}</LocalizedText>: {fmt(stressReference,3)}</p></div>
    </div>
    <div className="overview-operational-state"><span className={`status-dot ${warning===true?'red':''}`}/><strong><LocalizedText>{!available?'UNAVAILABLE':warning===true?'WARNING':warning===false?'Operational warning not triggered':'Operational warning state unavailable'}</LocalizedText></strong>{!korea&&<span><LocalizedText>{'Existing U.S. score band'}</LocalizedText>: <LocalizedText>{state}</LocalizedText></span>}</div>
    <div className="overview-stress-state"><LocalizedText>{typeof latest?.is_stress_event==='boolean'?latest.is_stress_event?'STRESS EVENT':'Stress Event threshold not reached':'Stress Event state unavailable'}</LocalizedText></div>
    <div className="overview-input-strip">{metrics.map(([label,value],index)=><div key={label}><span><LocalizedText>{label}</LocalizedText></span><strong>{value}</strong><small>{index===0?sourceDate(korea?'KOSPI200':'SPY'):index===1?sourceDate(korea?'VKOSPI':'VIX'):`${sourceDate(korea?'Korea_Treasury_3Y':'DGS10')} / ${sourceDate(korea?'Korea_Corporate_AAminus_3Y':'DBAA')}`}</small></div>)}</div>
    <footer className="monitor-caption"><LocalizedText>{'Data date'}</LocalizedText>: {latest?.last_updated||'—'} · <LocalizedText>{'Being below the warning threshold does not rule out market shocks.'}</LocalizedText></footer>
  </article>;
}
