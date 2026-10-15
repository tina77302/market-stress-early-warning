'use client';

import { useEffect, useState } from 'react';
import { LocalizedText, useI18n } from '../i18n/provider';
import { Market, workspace } from './types';

type Outcome = { date: string; end_date: string; return_pct: number };
type Distribution = { status: string; n: number; median_pct: number|null; q25_pct: number|null; q75_pct: number|null; downside_q10_pct: number|null; negative_frequency: number|null; dispersion_iqr_pct: number|null; events: Outcome[] };
type Evidence = Distribution & {symbol:string; sector?:string; industry?:string; source:string; kind:string};
type MarketEvidence = {status:string; regime?:string; observation_date?:string; risk_score?:number; sectors:Evidence[]; benchmark?:Distribution & {label:string}};
type Sensitivity = {market:Market; status:string; weight:number; distribution:Distribution|null; evidence:{symbol:string; weight:number|null;level:string;instrument:string|null;n:number}[]};
export type StressReport = {methodology_version:string;valuation_at:string;markets:Record<Market,MarketEvidence>;exposure:{status:string;cash_weight:number|null;largest_security_weight:number|null;groups:Record<string,{label:string;weight:number|null}[]>};sensitivity:Sensitivity[];outlook:{status:string;market?:Market;distribution:Distribution|null}};

export function histogram(events:Outcome[]) {
  if(!events.length)return [];
  const values=events.map(e=>e.return_pct), min=Math.min(...values), max=Math.max(...values);
  if(min===max)return [{low:min,high:max,count:values.length}];
  const size=Math.min(10,Math.ceil(Math.sqrt(values.length))), step=(max-min)/size;
  const bins=Array.from({length:size},(_,i)=>({low:min+i*step,high:min+(i+1)*step,count:0}));
  for(const value of values)bins[Math.min(size-1,Math.floor((value-min)/step))].count++;
  return bins;
}

function OutcomeChart({data}:{data:Distribution}) {
  const {locale}=useI18n();
  const number=(v:number|null)=>v===null?'—':`${v.toLocaleString(locale,{maximumFractionDigits:1})}%`;
  const bins=histogram(data.events), maximum=Math.max(1,...bins.map(b=>b.count));
  return <div className="stress-outcomes"><div className="stress-stat-grid">
    {([['stress_n',String(data.n)],['stress_median',number(data.median_pct)],['stress_typical',`${number(data.q25_pct)} … ${number(data.q75_pct)}`],['stress_negative',number(data.negative_frequency===null?null:data.negative_frequency*100)],['stress_downside',number(data.downside_q10_pct)],['stress_dispersion',number(data.dispersion_iqr_pct)]] as const).map(([id,value])=><div key={id}><small><LocalizedText id={id}/></small><strong>{value}</strong></div>)}
  </div>{data.status==='AVAILABLE'?<><div className="stress-histogram" role="img" aria-label={locale.startsWith('ko')?'과거 조건부 10거래일 수익률 분포':'Historical conditional 10-session return distribution'}>{bins.map((bin,i)=><div key={i} style={{height:`${Math.max(2,bin.count/maximum*100)}%`}} title={`${number(bin.low)} … ${number(bin.high)}: ${bin.count}`}><span>{bin.count}</span></div>)}</div><div className="stress-histogram-axis"><span>{number(bins[0]?.low??null)}</span><span>{number(bins[bins.length-1]?.high??null)}</span></div>{data.downside_q10_pct===null&&<p className="comparison-note"><LocalizedText id="stress_tail_insufficient"/></p>}</>:<p className="comparison-note"><LocalizedText id="stress_insufficient"/></p>}</div>;
}

export function StressAnalysisView({data}:{data:StressReport}) {
  const {locale}=useI18n();const [market,setMarket]=useState<Market>(()=>data.sensitivity.find(row=>row.evidence.length>0)?.market??'us');const [dimension,setDimension]=useState('sector');
  const selected=data.markets[market], sensitivity=data.sensitivity.find(row=>row.market===market);
  const percent=(n:number|null|undefined)=>n==null?'—':`${(n*100).toLocaleString(locale,{maximumFractionDigits:1})}%`;
  const returns=(n:number|null)=>n==null?'—':`${n.toLocaleString(locale,{maximumFractionDigits:1})}%`;
  return <section className="history-panel stress-analysis"><div className="rw-section-heading"><div><div className="eyebrow"><LocalizedText id="stress_identity"/></div><h2><LocalizedText id="stress_flow"/></h2></div><div className="market-switcher">{(['us','korea'] as const).map(m=><button key={m} aria-pressed={market===m} onClick={()=>setMarket(m)}><LocalizedText id={m==='us'?'u_s_usd_e1d876':'korea_krw_07f26e'}/></button>)}</div></div>
    <p className="comparison-note"><LocalizedText id="stress_conditional"/></p>
    <div className="stress-flow-grid">
      <article><h3><LocalizedText id="stress_step1"/></h3><strong className="stress-current">{selected.regime?<LocalizedText>{selected.regime}</LocalizedText>:'—'} · {selected.risk_score??'—'} / 100</strong><p className="comparison-note">{selected.observation_date??'—'}</p>{selected.status!=='AVAILABLE'&&<p><LocalizedText id="stress_current_missing"/></p>}
        {selected.benchmark&&<details><summary><LocalizedText id="stress_benchmark"/> · {selected.benchmark.label}</summary><p className="comparison-note"><LocalizedText id="stress_benchmark_note"/></p><OutcomeChart data={selected.benchmark}/></details>}
      </article>
      <article><h3><LocalizedText id="stress_step2"/></h3>{selected.sectors.length?selected.sectors.map(item=><details key={item.symbol}><summary>{item.kind==='sector'?item.sector:item.industry} · {item.symbol}<span className="stress-sector-reading"><LocalizedText id="stress_median"/> {returns(item.median_pct)} · <LocalizedText id="stress_n"/> {item.n}</span></summary><OutcomeChart data={item}/><a href={item.source} target="_blank" rel="noreferrer"><LocalizedText id="stress_source"/></a></details>):<p className="comparison-note"><LocalizedText id="stress_sector_missing"/></p>}</article>
      <article><h3><LocalizedText id="stress_step3"/></h3><div className="stress-dimensions">{(['market','sector','industry','currency','symbol'] as const).map(d=><button key={d} aria-pressed={dimension===d} onClick={()=>setDimension(d)}><LocalizedText id={`stress_dimension_${d}`}/></button>)}</div>
        {data.exposure.status!=='AVAILABLE'?<p><LocalizedText id="stress_valuation_missing"/></p>:<>{data.exposure.groups[dimension].map(row=><div className="stress-exposure" key={row.label}><span>{row.label.includes('UNKNOWN')?<><LocalizedText id={row.label.startsWith('korea:')?'korea_krw_07f26e':'u_s_usd_e1d876'}/> · <LocalizedText id="stress_unknown"/></>:(row.label.startsWith('us:')||row.label.startsWith('korea:'))?<><LocalizedText id={row.label.startsWith('korea:')?'korea_krw_07f26e':'u_s_usd_e1d876'}/> · {row.label.slice(row.label.indexOf(':')+1)}</>:row.label}</span><strong>{percent(row.weight)}</strong><i style={{width:`${Math.min(100,Math.max(0,(row.weight??0)*100))}%`}}/></div>)}<p className="comparison-note"><LocalizedText id="stress_cash"/> {percent(data.exposure.cash_weight)} · <LocalizedText id="stress_concentration"/> {percent(data.exposure.largest_security_weight)}</p><p className="comparison-note"><LocalizedText id="stress_exposure_note"/></p></>}
      </article>
      <article><h3><LocalizedText id="stress_step4"/></h3>{sensitivity?.evidence.length?<><ul className="stress-evidence">{sensitivity.evidence.map(row=><li key={row.symbol}><strong>{row.symbol}</strong> {percent(row.weight)} · <LocalizedText id={row.level==='security'?'stress_security':row.level==='sector_proxy'?'stress_proxy':'stress_evidence_missing'}/>{row.instrument&&` · ${row.instrument}`} · <LocalizedText id="stress_n"/> {row.n}</li>)}</ul>{sensitivity.distribution?<details><summary><LocalizedText id="stress_contribution_distribution"/></summary><OutcomeChart data={sensitivity.distribution}/></details>:<p className="comparison-note"><LocalizedText id="stress_evidence_missing"/></p>}</>:<p className="comparison-note"><LocalizedText id="stress_no_holdings"/></p>}<p className="comparison-note"><LocalizedText id="stress_contribution_note"/></p></article>
      <article className="stress-outlook"><h3><LocalizedText id="stress_step5"/></h3>{data.outlook.market&&<span className="rw-tag"><LocalizedText id={data.outlook.market==='us'?'u_s_usd_e1d876':'korea_krw_07f26e'}/></span>}{data.outlook.distribution?<OutcomeChart data={data.outlook.distribution}/>:<p className="comparison-note"><LocalizedText id={data.outlook.status==='NO_HOLDINGS'?'stress_no_holdings':data.outlook.status==='SEPARATE_MARKET_EVIDENCE_REQUIRED'?'stress_joint_missing':'stress_evidence_missing'}/></p>}<p className="comparison-note"><LocalizedText id="stress_outlook_note"/></p></article>
    </div><details><summary><LocalizedText id="stress_method"/></summary><p className="comparison-note"><LocalizedText id="stress_distribution_help"/></p><p className="comparison-note"><LocalizedText id="stress_method_note"/></p><p className="comparison-note">{data.methodology_version} · {new Date(data.valuation_at).toLocaleString(locale)}</p></details>
  </section>;
}

export default function StressAnalytics({userId,valuationAt}:{userId:number;valuationAt?:string}) {
  const key=`${userId}:${valuationAt??''}`;
  const [state,setState]=useState<{key:string;data:StressReport|null;error:boolean}|null>(null);
  useEffect(()=>{const controller=new AbortController();void workspace<StressReport>('paper/stress-analytics',{signal:controller.signal}).then(data=>{if(!controller.signal.aborted)setState({key,data,error:false});}).catch(()=>{if(!controller.signal.aborted)setState({key,data:null,error:true});});return()=>controller.abort();},[key]);
  if(state?.key===key&&state.data)return <StressAnalysisView data={state.data}/>;
  return <section className="history-panel stress-analysis" role="status"><h2><LocalizedText id="stress_identity"/></h2><p><LocalizedText id={state?.key===key&&state.error?'stress_load_error':'stress_loading'}/></p></section>;
}
