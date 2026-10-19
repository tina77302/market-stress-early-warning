'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Market } from './market-data';
import { MonitoringRecord, MonitoringLatest, MonitoringHistory, recordsForMarket } from './monitoring-data';

export function useMonitoring(market: Market) {
  const [state,setState] = useState<{market:Market; latest:MonitoringLatest|null; live:MonitoringRecord[]; retrospective:MonitoringRecord[]; loading:boolean; error:boolean; cursors:Record<'LIVE'|'RETROSPECTIVE',number|null>}>({market,latest:null,live:[],retrospective:[],loading:true,error:false,cursors:{LIVE:null,RETROSPECTIVE:null}});
  const [revision,setRevision] = useState(0);
  const generation=useRef(0);
  useEffect(() => {
    generation.current++;
    const controller = new AbortController();
    setState({market,latest:null,live:[],retrospective:[],loading:true,error:false,cursors:{LIVE:null,RETROSPECTIVE:null}});
    async function get(path:string) {
      const response = await fetch(`/api/monitoring/${path}`,{signal:controller.signal,cache:'no-store'});
      if (!response.ok) throw new Error('Monitoring unavailable');
      return response.json();
    }
    void Promise.allSettled([get(`latest?market=${market}`),get(`history?market=${market}&limit=500`),get(`history?market=${market}&record_type=RETROSPECTIVE&limit=500`)]).then(([latest,live,retro]) => {
      if (controller.signal.aborted) return;
      const result = latest.status==='fulfilled' && latest.value?.market===market ? latest.value as MonitoringLatest : null;
      const liveRows = live.status==='fulfilled' && (!live.value.market || live.value.market===market) ? Array.from(new Map(recordsForMarket(live.value.records,market,'LIVE').map(row=>[row.record_id,row])).values()) : [];
      const latestRecord = result?.record ? recordsForMarket([result.record],market,'LIVE')[0] : null;
      // A concurrently newer latest publication remains visible without changing publication order.
      const records = (latestRecord && !liveRows.some(row=>row.record_id===latestRecord.record_id) ? [latestRecord,...liveRows] : liveRows).sort((a,b)=>b.publication_sequence-a.publication_sequence);
      const validLatest=result && (result.record===null || latestRecord);
      const newest=records[0]??null;
      setState({market,latest:validLatest?{...result,record:newest,current_data_health:newest?.record_id===latestRecord?.record_id?result.current_data_health:{status:'UNAVAILABLE'}}:null,live:records,
        retrospective:retro.status==='fulfilled'&&(!retro.value.market||retro.value.market===market)?Array.from(new Map(recordsForMarket(retro.value.records,market,'RETROSPECTIVE').map(row=>[row.record_id,row])).values()):[],loading:false,
        error:!validLatest || [latest,live,retro].some(result=>result.status==='rejected'),
        cursors:{LIVE:live.status==='fulfilled'?live.value.next_before_sequence:null,RETROSPECTIVE:retro.status==='fulfilled'?retro.value.next_before_sequence:null}});
    });
    return () => {controller.abort();generation.current++;};
  },[market,revision]);
  const loadMore = useCallback(async (type:'LIVE'|'RETROSPECTIVE') => {
    const cursor=state.cursors[type]; if (!cursor) return;
    const requestGeneration=generation.current;
    try {
      const response=await fetch(`/api/monitoring/history?market=${market}&record_type=${type}&limit=500&before_sequence=${cursor}`,{cache:'no-store'});
      if (!response.ok) throw new Error('Monitoring unavailable');
      const page:MonitoringHistory=await response.json();
      setState(previous=>{
        if(previous.market!==market || generation.current!==requestGeneration)return previous;
        const key=type==='LIVE'?'live':'retrospective'; const existing=previous[key];
        const additions=recordsForMarket(page.records,market,type).filter(row=>!existing.some(old=>old.record_id===row.record_id));
        return {...previous,[key]:[...existing,...additions],cursors:{...previous.cursors,[type]:page.next_before_sequence}};
      });
    } catch {setState(previous=>previous.market===market && generation.current===requestGeneration?{...previous,error:true}:previous);}
  },[market,state.cursors]);
  const visible=state.market===market?state:{market,latest:null,live:[],retrospective:[],loading:true,error:false,cursors:{LIVE:null,RETROSPECTIVE:null}};
  return {...visible,retry:()=>setRevision(value=>value+1),loadMore};
}
