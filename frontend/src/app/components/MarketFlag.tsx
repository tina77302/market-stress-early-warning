'use client';
import { useI18n } from '../i18n/provider';
import type { Market } from './market-data';
/** Local vector flags avoid platform-dependent emoji fonts. */
export default function MarketFlag({market}:{market:Market}) {
 const {t}=useI18n();
 return market==='korea'?<svg className="mc-market-flag" width="26" height="19" viewBox="0 0 32 24" role="img" aria-label={t('Korea Market')}><rect width="32" height="24" rx="2" fill="#f3f6fa"/><circle cx="16" cy="12" r="6" fill="#d74458"/><path d="M10 12a6 6 0 0012 0c0-4-6-4-6 0s-6 4-6 0" fill="#236bb4"/>{[[5,5,35],[25,5,-35],[5,19,-35],[25,19,35]].map(([x,y,r],i)=><g key={i} transform={`translate(${x} ${y}) rotate(${r})`} stroke="#263442" strokeWidth="1"><path d="M-2-2h4M-2 0h4M-2 2h4"/></g>)}</svg>:<svg className="mc-market-flag" width="26" height="19" viewBox="0 0 32 24" role="img" aria-label={t('U.S. Market')}><rect width="32" height="24" rx="2" fill="#f4f6fa"/>{[0,4,8,12,16,20].map(y=><rect key={y} y={y} width="32" height="2" fill="#d94b60"/>)}<rect width="14" height="13" fill="#285b99"/>{[3,7,11].flatMap(x=>[3,6,9].map(y=><circle key={`${x}-${y}`} cx={x} cy={y} r=".6" fill="white"/>))}</svg>;
}
