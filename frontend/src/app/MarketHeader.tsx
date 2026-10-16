'use client';

import { LocalizedText, useI18n, LanguageSwitcher } from './i18n/provider';


import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ShieldAlert } from 'lucide-react';
import AccountMenu from './components/AccountMenu';

export default function MarketHeader() {
  const { t, locale } = useI18n();

  const path = usePathname();
  const korea = path.startsWith('/korea');
  const links = [
    { href: '/', label: 'Overview', active: path === '/' },
    { href: '/us', label: 'U.S. Market', active: path === '/us' },
    { href: '/korea', label: 'Korea Market', active: path === '/korea' },
    { href: '/compare', label: 'Compare', active: path === '/compare' },
    { href: '/paper-trading', label: 'Multi-Asset / Paper Trading', active: path === '/paper-trading' },
    { href: korea ? '/korea/validation' : '/validation', label: 'Validation', active: path === '/validation' || path === '/korea/validation' },
    { href: korea ? '/korea/methodology' : '/methodology', label: 'Methodology', active: path === '/methodology' || path === '/korea/methodology' },
  ];
  return <header className="home-nav product-nav">
    <Link href="/" className="home-brand"><ShieldAlert size={27}/><span><LocalizedText id="market_risk_intelligence_b27728"/></span><small><LocalizedText id="ai_early_warning_system_dfd87f"/></small></Link>
    <nav aria-label={t("Main navigation")}>{links.map(({ href, label, active }) => <Link key={label} href={href} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined}><LocalizedText>{label}</LocalizedText></Link>)}</nav>
    <div className="header-preferences"><LanguageSwitcher/><AccountMenu/></div>
  </header>;
}
