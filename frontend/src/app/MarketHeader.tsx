'use client';

import { LocalizedText, useI18n, LanguageSwitcher } from './i18n/provider';


import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ShieldAlert, BarChart3, ArrowLeftRight, Wallet, Activity, BookOpen, Layers, BriefcaseBusiness } from 'lucide-react';
import AccountMenu from './components/AccountMenu';
import MarketFlag from './components/MarketFlag';

export default function MarketHeader() {
  const { t, locale } = useI18n();

  const path = usePathname();
  const korea = path.startsWith('/korea');
  const consolePage=['/','/us','/korea'].includes(path);
  const links = [
    { href: '/', label: 'Overview', active: path === '/' },
    { href: '/us', label: 'U.S. Market', active: path === '/us' },
    { href: '/korea', label: 'Korea Market', active: path === '/korea' },
    { href: '/compare', label: 'Compare', active: path === '/compare' },
    ...(consolePage ? [{href: `${korea?'/korea':'/us'}#industry-research`,label:'Industry Research',active:false}] : []),
    { href: '/paper-trading', label: consolePage ? 'Paper Trading' : 'Multi-Asset / Paper Trading', active: path === '/paper-trading' },
    ...(consolePage ? [{href:'/paper-trading#portfolio-workspace',label:'Portfolio',active:false}] : []),
    { href: korea ? '/korea/validation' : '/validation', label: 'Validation', active: path === '/validation' || path === '/korea/validation' },
    { href: korea ? '/korea/methodology' : '/methodology', label: 'Methodology', active: path === '/methodology' || path === '/korea/methodology' },
  ];
  return <>{consolePage&&<div className="mc-topbar"><Link className="mc-top-brand" href="/"><ShieldAlert size={20}/><span>{'MARKET RISK INTELLIGENCE'}</span><small>{'AI EARLY WARNING SYSTEM'}</small></Link><nav aria-label={t('Console navigation')}>{links.filter(link=>!link.href.includes('#')).map(link=><Link key={link.href} href={link.href} aria-current={link.active?'page':undefined}><LocalizedText>{link.label}</LocalizedText></Link>)}</nav><div className="header-preferences"><LanguageSwitcher/><AccountMenu/></div></div>}<header className="home-nav product-nav">
    <Link href="/" className="home-brand"><ShieldAlert size={27}/><span><LocalizedText id="market_risk_intelligence_b27728"/></span><small><LocalizedText id="ai_early_warning_system_dfd87f"/></small></Link>
    <nav aria-label={t("Main navigation")}>{links.map(({ href, label, active }) => <Link key={label} href={href} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined}>{consolePage&&<span className="mc-nav-icon" aria-hidden="true">{href==='/korea'?<MarketFlag market="korea"/>:href==='/us'?<MarketFlag market="us"/>:href==='/'?<BarChart3 size={17}/>:href==='/compare'?<ArrowLeftRight size={17}/>:href.includes('industry-research')?<Layers size={17}/>:href.includes('portfolio-workspace')?<BriefcaseBusiness size={17}/>:href==='/paper-trading'?<Wallet size={17}/>:href.includes('validation')?<Activity size={17}/>:<BookOpen size={17}/>}</span>}<LocalizedText>{label}</LocalizedText></Link>)}</nav>
    {!consolePage&&<div className="header-preferences"><LanguageSwitcher/><AccountMenu/></div>}
  </header></>;
}
