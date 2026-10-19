'use client';
import Link from 'next/link';
import Image from 'next/image';
import { Activity, ArrowUpRight, Clock3, Globe2 } from 'lucide-react';
import { LocalizedText, useI18n } from '../i18n/provider';
import type { HistoryPoint, Latest, Market } from './market-data';
import { fmt } from './market-data';
import { publicationTime } from './monitoring-data';
import { BuildUpPreview, CompactMarketState } from './MonitoringConsole';
import MarketFlag from './MarketFlag';
function Text({children}:{children:string}) { return <LocalizedText>{children}</LocalizedText>; }
export function GlobalHero({us,korea}:{us:Latest|null;korea:Latest|null}) {
 const {t,locale}=useI18n();
 const indicators=[{label:'SPY',value:us?.spy_price,date:us?.last_updated,suffix:' USD'},{label:'KOSPI200',value:korea?.kospi200,date:korea?.last_updated,suffix:''},{label:'VIX',value:us?.vix_level,date:us?.last_updated,suffix:''},{label:'VKOSPI',value:korea?.vkospi,date:korea?.last_updated,suffix:''},{label:'Baa–Treasury (pp)',value:us?.baa_treasury_spread,date:us?.last_updated,suffix:''}];
 return <section className="mc-global-hero" aria-labelledby="mc-global-title"><div className="mc-global-copy"><span className="mc-eyebrow"><Globe2 size={13}/>{'MARKET STRESS EARLY WARNING SYSTEM'}</span><h1 id="mc-global-title"><Text>{'Monitor Global Market Stress'}</Text><br/><span><Text>{'Before the Threshold'}</Text></span></h1><strong lang="en">{'Beyond the Threshold — Track the Risk Build-Up.'}</strong><p><Text>{'Equity, volatility and credit. Two markets. One monitoring command center.'}</Text></p><div className="mc-global-scope"><span><i/><Text>{'United States'}</Text></span><span><i/><Text>{'Korea'}</Text></span><small><Text>{'Independent market models'}</Text></small></div></div>
  <div className="mc-global-globe" role="img" aria-label={t('Decorative globe connecting the U.S. and Korea; not analytical evidence')}><Image src="/monitoring/globe.svg" alt="" width={600} height={580} priority/><Link className="mc-globe-market mc-globe-korea" href="/korea"><MarketFlag market="korea"/><Text>{'Korea'}</Text><ArrowUpRight size={12}/></Link><Link className="mc-globe-market mc-globe-us" href="/us"><MarketFlag market="us"/><Text>{'U.S.'}</Text><ArrowUpRight size={12}/></Link></div>
  <aside className="mc-global-aside"><div className="mc-publication-status"><h2><Clock3 size={13}/><Text>{'Publication status'}</Text></h2>{([{market:'us',latest:us},{market:'korea',latest:korea}] as const).map(({market,latest})=><div key={market}><span><MarketFlag market={market}/><Text>{market==='us'?'U.S.':'Korea'}</Text><b data-health={latest?.data_health?.status??'UNAVAILABLE'}><Text>{latest?.data_health?.status??'UNAVAILABLE'}</Text></b></span><small><Text>{'Published At'}</Text> · {publicationTime(latest?.data_health?.published_at??null,locale)}</small></div>)}</div><section className="mc-card mc-global-indicators"><header><Activity size={15}/><h2><Text>{'Key Global Indicators'}</Text></h2></header><dl>{indicators.map(row=><div key={row.label}><dt><Text>{row.label}</Text><small>{row.date??'—'}</small></dt><dd>{fmt(row.value,2,row.suffix)}</dd></div>)}</dl></section></aside>
 </section>;
}
export function CommandMarketCard({market,latest,history}:{market:Market;latest:Latest|null;history:HistoryPoint[]}) {
 return <article className={`mc-card mc-command-card mc-city-${market}`} data-market={market}><CompactMarketState market={market} latest={latest}/><BuildUpPreview market={market} history={history}/></article>;
}
