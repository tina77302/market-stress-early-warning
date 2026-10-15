'use client';

import { useEffect, useId, useRef, useState, KeyboardEvent } from 'react';
import { LocalizedText, useI18n } from '../i18n/provider';
import { Market, Security, workspace } from './types';

export function SearchResults({ items, active, listId, onSelect, onActive }: { items: Security[]; active: number; listId: string; onSelect: (item: Security) => void; onActive: (index: number) => void }) {
  return <ul id={listId} role="listbox" className="security-results">{items.map((item,index) => <li key={item.symbol} id={`${listId}-${index}`} role="option" aria-selected={index===active} onMouseDown={event=>event.preventDefault()} onClick={()=>onSelect(item)} onMouseEnter={()=>onActive(index)}>
    <div><strong>{item.ticker}</strong><span>{item.name}</span></div><small>{item.exchange} · <LocalizedText>{item.market==='us'?'U.S.':'Korea'}</LocalizedText> · <LocalizedText id={item.security_type==='ETF'?'security_type_etf':'security_type_stock'}/></small>
  </li>)}</ul>;
}

export default function SecurityPicker({ market, disabled, onSelect, onSearchStart }: { market: Market; disabled: boolean; onSelect: (security: Security) => void; onSearchStart: () => void }) {
  const { t } = useI18n();
  const [query,setQuery] = useState('');
  const [items,setItems] = useState<Security[]>([]);
  const [active,setActive] = useState(-1);
  const [open,setOpen] = useState(false);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState('');
  const [stale,setStale] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const request = useRef<AbortController | null>(null);
  const listId = useId();
  useEffect(()=>{
    const controller = new AbortController();request.current=controller;
    setItems([]);setActive(-1);setError('');setStale(false);
    if (!query.trim() || disabled) {setLoading(false);return ()=>controller.abort();}
    setLoading(true);
    const timer=setTimeout(()=>{
      void workspace<{ data: Security[]; directory_status?: string }>(`paper/securities?market=${market}&q=${encodeURIComponent(query.trim())}&limit=20`,{signal:controller.signal}).then(result=>{
        if(controller.signal.aborted)return;
        setItems(result.data);setActive(-1);setStale(result.directory_status==='STALE');
      }).catch(()=>{if(!controller.signal.aborted)setError('Security search is temporarily unavailable. Try again.');})
        .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    },300);
    return ()=>{clearTimeout(timer);controller.abort();};
  },[query,market,disabled]);
  useEffect(()=>{
    function outside(event: PointerEvent){if(root.current&&!root.current.contains(event.target as Node))setOpen(false);}
    document.addEventListener('pointerdown',outside);
    return ()=>document.removeEventListener('pointerdown',outside);
  },[]);
  useEffect(()=>{if(active>=0)document.getElementById(`${listId}-${active}`)?.scrollIntoView({block:'nearest'});},[active,listId]);
  function choose(item:Security){request.current?.abort();onSelect(item);setQuery('');setItems([]);setOpen(false);setActive(-1);}
  function keyboard(event:KeyboardEvent<HTMLInputElement>){
    if(event.key==='Escape'){setOpen(false);setActive(-1);return;}
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault();setOpen(true);
      if(items.length)setActive(index=>event.key==='ArrowDown'?(index+1)%items.length:(index<=0?items.length-1:index-1));
    }
    if(event.key==='Enter'){
      // Free text can never become an execution symbol.
      event.preventDefault();if(open&&active>=0&&items[active])choose(items[active]);
    }
  }
  return <div className="security-picker" ref={root} onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))setOpen(false);}}>
    <label><LocalizedText id="security_search_label"/><input role="combobox" aria-autocomplete="list" aria-expanded={open&&items.length>0} aria-controls={listId} aria-activedescendant={open&&active>=0?`${listId}-${active}`:undefined} value={query} disabled={disabled} maxLength={100} autoComplete="off" placeholder={t('Search by company name or ticker')} onKeyDown={keyboard} onFocus={()=>setOpen(true)} onChange={event=>{request.current?.abort();setQuery(event.target.value);setOpen(true);setItems([]);setActive(-1);onSearchStart();}}/></label>
    <div className="security-result-anchor">{open&&items.length>0&&<SearchResults items={items} active={active} listId={listId} onSelect={choose} onActive={setActive}/>}</div>
    <div className="security-search-status" role="status" aria-live="polite">{loading?<LocalizedText id="security_search_loading"/>:error?<LocalizedText>{error}</LocalizedText>:query.trim()&&open&&!items.length?<LocalizedText id="security_search_empty"/>:<LocalizedText id="security_search_hint"/>}</div>
    {stale&&<p className="comparison-note amber"><LocalizedText id="security_directory_stale"/></p>}
  </div>;
}
