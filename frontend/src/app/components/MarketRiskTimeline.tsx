'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { LocalizedText, useI18n } from '../i18n/provider';
import { fmt, HistoryPoint, Market } from './market-data';
import { availablePoints, combinedPoints, buildUpWindow, pointSourceLabel, pointTrajectory, MonitoringLatest, MonitoringRecord, provenance, publicationPoints, publicationTime, TimelinePoint, TimelineSource, trajectory } from './monitoring-data';
import { useMonitoring } from './use-monitoring';

const stateLabel = (value:boolean|null|undefined) => value===true?'Triggered':value===false?'Not triggered':'Not recorded';
function Pair({label,value}:{label:string;value:React.ReactNode}) {
  return <div><dt><LocalizedText>{label}</LocalizedText></dt><dd>{value}</dd></div>;
}
export function LivePublication({latest,loading,error,retry}:{latest:MonitoringLatest|null;loading:boolean;error:boolean;retry:()=>void}) {
  const {locale,t}=useI18n(); const record=latest?.record;
  return <section className={`live-publication live-status${!record?' is-empty':''}`} aria-label={t('LIVE MONITORING')}>
    <header><span className="publication-badge"><LocalizedText>{'LIVE'}</LocalizedText></span><h2><LocalizedText>{loading?'Loading publication ledger…':!latest?'Publication ledger unavailable':!record?'LIVE Monitoring — Awaiting first prospective publication':'Latest Published Observation'}</LocalizedText></h2>{record&&<span className="live-status-observation">{record.observation_date} · {fmt(record.risk_score,1)} / 100</span>}<button type="button" className="refresh-publications" disabled={loading} onClick={retry}><LocalizedText>{'Refresh publications'}</LocalizedText></button></header>
    {record&&<details><summary><LocalizedText>{'Publication details'}</LocalizedText></summary><dl className="publication-grid">
      <Pair label="Observation Date" value={<time dateTime={record.observation_date}>{record.observation_date}</time>}/>
      <Pair label="Published At" value={<time dateTime={record.generated_at}>{publicationTime(record.generated_at,locale)}</time>}/>
      <Pair label="Risk Score" value={fmt(record.risk_score,1)}/><Pair label="MSI" value={fmt(record.msi,3)}/>
      <Pair label="Operational Warning" value={<LocalizedText>{stateLabel(record.operational_warning)}</LocalizedText>}/>
      <Pair label="MSI Stress Event" value={<LocalizedText>{stateLabel(record.msi_stress_event)}</LocalizedText>}/>
      <Pair label="Data Health now" value={<span className="data-status"><LocalizedText>{latest?.current_data_health?.status??'UNAVAILABLE'}</LocalizedText></span>}/>
      <Pair label="Model / Input audit" value={<LocalizedText>{provenance(record)}</LocalizedText>}/>
    </dl></details>}
    {error&&<p className="monitoring-error" role="status"><LocalizedText>{'Some monitoring requests failed. Available records remain visible.'}</LocalizedText></p>}
  </section>;
}

function TrackChart({points,selected,onSelect}:{points:TimelinePoint[];selected:string;onSelect:(date:string)=>void}) {
  const {t}=useI18n();const host=useRef<HTMLDivElement>(null);const [canvasWidth,setCanvasWidth]=useState(900);
  useEffect(()=>{if(!host.current)return;const observer=new ResizeObserver(entries=>{const width=entries[0]?.contentRect.width;if(width>0)setCanvasWidth(Math.max(240,Math.round(width)));});observer.observe(host.current);return ()=>observer.disconnect();},[]);
  if(!points.length)return null;
  const left=42,right=canvasWidth-48,dates=points.map(p=>Date.parse(p.date+'T00:00:00Z')),start=dates[0],span=dates.at(-1)!-start||1;
  const x=(i:number)=>points.length===1?(left+right)/2:left+(dates[i]-start)/span*(right-left);
  const scoreY=(value:number)=>220-value/100*185;
  const maxMSI=Math.max(1,...points.map(p=>p.msi??0))*1.1,minMSI=Math.min(0,...points.map(p=>p.msi??0));
  const msiY=(value:number)=>220-(value-minMSI)/(maxMSI-minMSI)*185;
  const returns=points.map(p=>p.movement).filter((v):v is number=>v!==null);const maxReturn=Math.max(1,...returns.map(Math.abs));
  const returnY=(value:number)=>270-value/maxReturn*22;
  const path=(field:'score'|'msi',scale:(v:number)=>number)=>points.map((p,i)=>p[field]===null?'':`${i===0||points[i-1][field]===null||points[i-1].source!==p.source?'M':'L'}${x(i)},${scale(p[field]!)}`).join(' ');
  const selectedIndex=points.findIndex(p=>(p.id===selected||p.date===selected));
  return <div ref={host} className="trajectory-chart-scroll"><svg className="trajectory-chart" viewBox={`0 0 ${canvasWidth} 330`} role="img" aria-label={t('Risk Score, MSI and market movement on the same observation-date axis')} onClick={event=>{const svg=event.currentTarget,matrix=svg.getScreenCTM();if(!matrix)return;const pointer=svg.createSVGPoint();pointer.x=event.clientX;pointer.y=event.clientY;const location=pointer.matrixTransform(matrix.inverse());const nearest=points.reduce((best,_,i)=>Math.hypot(x(i)-location.x,scoreY(points[i].score??0)-location.y)<Math.hypot(x(best)-location.x,scoreY(points[best].score??0)-location.y)?i:best,0);onSelect(points[nearest].id);}}>
    <title>{t('Market Risk Timeline')}</title>
    {[0,50,100].map(value=><g key={value}><text x={left-10} y={scoreY(value)+4} textAnchor="end">{value}</text>{value===50&&<line className="operational-reference" x1={left} x2={right} y1={scoreY(value)} y2={scoreY(value)} stroke="#ee8666" strokeDasharray="6 5"/>}</g>)}
    <text x={left} y="17" className="track-label">{t('Risk Score')}</text><text x={right} y="17" textAnchor="end" className="track-label">{t('MSI')}</text>
    {[minMSI,(maxMSI+minMSI)/2,maxMSI].map(value=><text key={value} x={right+10} y={msiY(value)+4}>{fmt(value,1)}</text>)}
    <text x={right} y={scoreY(50)-7} textAnchor="end" className="threshold-label">{t('Operational threshold 50')}</text>
    <path d={path('msi',msiY)} className="msi-path"/><path d={path('score',scoreY)} className="score-path"/>
    {points.map((point,i)=><g key={point.id}>{point.score!==null&&<><circle className={`score-observation source-${point.source.toLowerCase()}`} cx={x(i)} cy={scoreY(point.score)} r={points.length<=20?4:2}><title>{`${point.date} · ${t(pointSourceLabel(point))} · ${fmt(point.score,1)}`}</title></circle>{points.length<=10&&<text className="score-point-label" x={x(i)} y={i>0&&points[i-1].date===point.date?scoreY(point.score)+20:scoreY(point.score)-12} textAnchor="middle">{fmt(point.score,1)}</text>}</>}{point.warning===true&&<rect x={x(i)-3} y="226" width="6" height="6" fill="#ef8e7f"/>}{point.stress===true&&<circle cx={x(i)} cy="239" r="3" fill="#b6a4ef"/>}</g>)}
    <text x={left} y="249" className="movement-track-label">{t('Market return (%)')}</text><line x1={left} x2={right} y1="270" y2="270" stroke="#284351"/>
    {points.map((p,i)=>p.movement!==null?<rect key={p.id} x={x(i)-Math.min(8,(right-left)/points.length/4)} y={Math.min(270,returnY(p.movement))} width={Math.min(16,(right-left)/points.length/2)} height={Math.max(1,Math.abs(returnY(p.movement)-270))} className="return-bar"><title>{`${p.date} · ${fmt(p.movement,2)}%`}</title></rect>:null)}
    {!returns.length&&<text x={(left+right)/2} y="291" textAnchor="middle">{t('Market return not recorded')}</text>}
    {selectedIndex>=0&&<line x1={x(selectedIndex)} x2={x(selectedIndex)} y1="30" y2="299" stroke="#7c9db2" strokeDasharray="3 5"/>}
    {Array.from(new Set([0,Math.floor((points.length-1)/2),points.length-1])).map(i=><text key={i} x={x(i)} y="319" textAnchor={i===0?'start':i===points.length-1?'end':'middle'}>{points[i].date.slice(5)}</text>)}
  </svg></div>;
}

type ProvenanceFilter = TimelineSource | 'ALL';
export function RiskTrajectory({market,history,live,retrospective,loadMore,cursors,status}:{market:Market;history:HistoryPoint[];live:MonitoringRecord[];retrospective:MonitoringRecord[];loadMore:(type:'LIVE'|'RETROSPECTIVE')=>void;cursors:Record<'LIVE'|'RETROSPECTIVE',number|null>;status?:React.ReactNode}) {
  const {t,locale}=useI18n(); const [source,setSource]=useState<ProvenanceFilter>('ALL');
  const [range,setRange]=useState(5); const [selection,setSelection]=useState<string|null>(null);
  const available=useMemo(()=>availablePoints(history,market,live,retrospective),[history,market,live,retrospective]);
  const all=useMemo(()=>combinedPoints(available),[available]);
  const dated=all; const points=buildUpWindow(all,range);
  const selected=points.find(p=>p.id===selection)??points.at(-1);
  const siblings=selected?all.filter(p=>p.date===selected.date).sort((a,b)=>(b.record?.publication_sequence??0)-(a.record?.publication_sequence??0)):[];
  const displayed=points;
  const changes=pointTrajectory(all,selected?.id??'');
  const change=changes.change;
  const direction=change===null?'Change unavailable':change>0?'Risk increasing':change<0?'Risk decreasing':'Risk unchanged';
  function choose(id:string){setSelection((points.find(p=>p.id===id)??points.find(p=>p.date===id&&p.source===source)??points.find(p=>p.date===id))?.id??null);}
  return <section className="risk-trajectory" aria-labelledby="risk-trajectory-title">
    <header className="trajectory-heading"><div><p className="eyebrow"><LocalizedText>{'BEYOND THE THRESHOLD'}</LocalizedText></p><h2 id="risk-trajectory-title"><LocalizedText>{'Beyond the Threshold'}</LocalizedText></h2><p><LocalizedText>{'Track the Risk Build-Up.'}</LocalizedText></p></div><span className="trajectory-market">{market==='korea'?'KOSPI200':'SPY'}</span></header>
    <div className="trajectory-controls"><div className="trajectory-sources" role="group" aria-label={t('Highlight provenance')}>{(['ALL','LIVE','RETROSPECTIVE','OOS'] as const).map(value=><button key={value} type="button" disabled={value!=='ALL'&&!available.some(point=>point.source===value)} aria-pressed={source===value} onClick={()=>{setSource(value);if(value!=='ALL')setSelection(points.find(p=>p.source===value)?.id??null);}}><LocalizedText>{value==='ALL'?'All observations':value==='OOS'?'HISTORICAL OOS':value}</LocalizedText></button>)}</div><label><LocalizedText>{'Observations'}</LocalizedText><select value={range} onChange={event=>setRange(Number(event.target.value))}>{[5,20,60,252,0].map(value=><option key={value} value={value}>{value||t('ALL')}</option>)}</select></label></div>
    <div className="trajectory-main" data-highlight-provenance={source}><div className="trajectory-plot">{!points.length?<div className="trajectory-empty"><LocalizedText>{source==='LIVE'?'No prospective LIVE publications yet. Historical observations are available under All observations.':source==='RETROSPECTIVE'?'No retrospective publications are recorded.':'No historical observations are available.'}</LocalizedText></div>:<>
      <div className="trajectory-sequence" aria-label={t('Recent Risk Score observations')}>{buildUpWindow(points,5).map(point=><button type="button" key={point.id} aria-pressed={selected?.id===point.id} onClick={()=>choose(point.id)} aria-label={`${point.date} · ${t(pointSourceLabel(point))} · ${fmt(point.score,1)}`}><time dateTime={point.date}>{point.date.slice(5)}</time><strong>{fmt(point.score,1)}</strong><span title={t(pointSourceLabel(point))}>{point.source==='RETROSPECTIVE'?'RETRO':point.source==='OOS'?'HIST. OOS':'LIVE'}</span></button>)}</div>
      <div className="trajectory-readout"><div><span><LocalizedText>{'SELECTED LEVEL'}</LocalizedText> · {selected?.date}</span><strong>{fmt(selected?.score,1)}<small>/100</small></strong></div><div><span><LocalizedText>{'DIRECTION'}</LocalizedText></span><strong><LocalizedText>{direction}</LocalizedText></strong></div><div><span><LocalizedText>{'CHANGE / OBSERVATION'}</LocalizedText></span><strong>{change!==null&&change>0?'+':''}{fmt(change,1)}<small><LocalizedText>{'pts'}</LocalizedText></small></strong></div><div><span><LocalizedText>{'UPWARD STEPS · LAST 5'}</LocalizedText></span><strong>{changes.risingSteps} / {changes.steps}</strong></div></div>
      <TrackChart points={displayed} selected={selected!.id} onSelect={choose}/>
      <div className="trajectory-legend"><span className="score-key"><LocalizedText>{'Risk Score'}</LocalizedText></span><span className="msi-key"><LocalizedText>{'MSI'}</LocalizedText></span><span className="movement-key"><LocalizedText>{'Market return (%)'}</LocalizedText></span><span><LocalizedText>{'Square: operational warning · dot: MSI Stress Event · shown only when recorded'}</LocalizedText></span></div>
    </>}</div><aside className="trajectory-live-aside">{status}<p><LocalizedText>{'Historical analysis is not a LIVE alert.'}</LocalizedText></p></aside></div>
    {points.length>0&&<>
      <p className="trajectory-source-note"><LocalizedText>{'Provenance is shown for every observation. Historical analysis is not a LIVE alert. Lines break when provenance changes.'}</LocalizedText></p>
      <div className="trajectory-date-workspace"><section className="trajectory-metrics"><header><h3><LocalizedText>{'Date-based metrics'}</LocalizedText></h3><span>{points.length} · <LocalizedText>{'Observations'}</LocalizedText></span></header><div className="trajectory-table-scroll"><table><thead><tr>{['Observation Date','Risk Score','Change from previous observation','MSI','Market return (%)','Provenance'].map(label=><th scope="col" key={label}><LocalizedText>{label}</LocalizedText></th>)}</tr></thead><tbody>{displayed.slice(-10).map(point=>{const delta=pointTrajectory(all,point.id).change;return <tr key={point.id} aria-selected={selected?.id===point.id} onClick={()=>choose(point.id)}><td><button type="button" onClick={()=>choose(point.id)}>{point.date}</button></td><td>{fmt(point.score,1)}</td><td>{delta!==null&&delta>0?'+':''}{fmt(delta,1)}</td><td>{fmt(point.msi,3)}</td><td>{fmt(point.movement,2)}{point.movement!==null?'%':''}</td><td><span className={`table-provenance source-${point.source.toLowerCase()}`}>{t(pointSourceLabel(point))}</span></td></tr>;})}</tbody></table></div></section><div className="trajectory-detail-panel">
      <div className="date-selector"><button type="button" disabled={points[0]?.id===selected?.id} onClick={()=>choose(points[Math.max(0,points.findIndex(p=>p.id===selected?.id)-1)].id)} aria-label={t('Previous observation')}>←</button><label><LocalizedText>{'Select observation date'}</LocalizedText><select value={selected?.id} onChange={event=>choose(event.target.value)}>{points.map(point=><option key={point.id} value={point.id}>{point.date} · {t(pointSourceLabel(point))}</option>)}</select></label><button type="button" disabled={points.at(-1)?.id===selected?.id} onClick={()=>choose(points[Math.min(points.length-1,points.findIndex(p=>p.id===selected?.id)+1)].id)} aria-label={t('Next observation')}>→</button></div>
      {siblings.length>1&&<label className="republication-selector"><LocalizedText>{'Evidence for this date'}</LocalizedText><select value={selected!.id} onChange={event=>setSelection(event.target.value)}>{siblings.map(point=><option key={point.id} value={point.id}>{t(pointSourceLabel(point))} · {point.archive?t(point.archive.basis):point.record?publicationTime(point.published,locale):t('Historical OOS analysis')}{point.record?` · #${point.record.publication_sequence}`:''}</option>)}</select></label>}
      <section className="trajectory-date-detail" aria-label={t('Selected observation detail')} aria-live="polite"><header><h3><LocalizedText>{'Date detail'}</LocalizedText></h3><span className="publication-badge">{t(pointSourceLabel(selected!))}</span></header><dl className="publication-grid">
        <Pair label="Observation Date" value={<time dateTime={selected!.date}>{selected!.date}</time>}/><Pair label="Published At" value={selected!.published?<time dateTime={selected!.published}>{publicationTime(selected!.published,locale)}</time>:<LocalizedText>{'Not recorded · no publication-time claim'}</LocalizedText>}/>
        <Pair label="Risk Score" value={fmt(selected!.score,1)}/><Pair label="Change from previous observation" value={`${change!==null&&change>0?'+':''}${fmt(change,1)}`}/><Pair label="MSI" value={fmt(selected!.msi,3)}/><Pair label="Market return (%)" value={fmt(selected!.movement,2)}/>
        <Pair label="Operational Warning" value={<LocalizedText>{stateLabel(selected!.warning)}</LocalizedText>}/><Pair label="MSI Stress Event" value={<LocalizedText>{stateLabel(selected!.stress)}</LocalizedText>}/><Pair label="Data Health at publication" value={<span className="data-status"><LocalizedText>{selected!.health??'Not recorded'}</LocalizedText></span>}/>
        <Pair label="Provenance" value={<><span>{t(pointSourceLabel(selected!))}</span>{selected!.archive&&<> · <LocalizedText>{selected!.archive.basis}</LocalizedText></>}</>}/><Pair label="Model / Input audit" value={<LocalizedText>{selected!.archive?'Archive fingerprints recorded':provenance(selected!.record)}</LocalizedText>}/>
      </dl>{selected!.archive&&<p className="trajectory-footnote"><LocalizedText>{'RETROSPECTIVE archive: stored snapshots and existing frozen-model replay. Returns are retrospective price-history calculations. Publication times are shown only for stored snapshots; historical Data Health is not recorded.'}</LocalizedText></p>}</section></div></div>
    </>}
    {(['LIVE','RETROSPECTIVE'] as const).filter(type=>(source==='ALL'||source===type)&&cursors[type]).map(type=><button key={type} type="button" className="load-publications" onClick={()=>loadMore(type)}><LocalizedText>{'Load earlier publications'}</LocalizedText> · {type}</button>)}
    <p className="trajectory-footnote"><LocalizedText>{'Only the existing threshold 50 activates the operational warning. A score below 50 does not mean safe.'}</LocalizedText></p>
  </section>;
}

export default function MarketRiskTimeline({market,history}:{market:Market;history:HistoryPoint[]}) {
  const monitoring=useMonitoring(market);
  return <div className="monitoring-experience"><RiskTrajectory status={<LivePublication latest={monitoring.latest} loading={monitoring.loading} error={monitoring.error} retry={monitoring.retry}/>} key={market} market={market} history={history} live={monitoring.live} retrospective={monitoring.retrospective} cursors={monitoring.cursors} loadMore={monitoring.loadMore}/></div>;
}
