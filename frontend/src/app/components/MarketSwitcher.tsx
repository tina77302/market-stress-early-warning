'use client';

import { LocalizedText, useI18n } from '../i18n/provider';
import Link from 'next/link';
import { Market } from './market-data';

export default function MarketSwitcher({ market, section }: { market: Market; section: 'validation' | 'methodology' }) {
  const { t, locale } = useI18n();

  return <nav className="market-switcher" aria-label={t(String(`${section === 'validation' ? 'Validation' : 'Methodology'} market`))}>
    <Link href={`/${section}`} aria-current={market === 'us' ? 'page' : undefined} className={market === 'us' ? 'selected' : undefined}><LocalizedText id="u_s_7a3239"/></Link>
    <Link href={`/korea/${section}`} aria-current={market === 'korea' ? 'page' : undefined} className={market === 'korea' ? 'selected' : undefined}><LocalizedText id="korea_4e8bd0"/></Link>
  </nav>;
}
