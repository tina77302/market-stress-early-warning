'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';
import {
  ShieldAlert,
  BarChart3,
  Activity,
  FlaskConical,
} from 'lucide-react';

export default function MarketHeader() {
  const pathname = usePathname();

  const isKorea = pathname.startsWith('/korea');

  const marketName = isKorea
    ? 'KOREA MARKET RISK INTELLIGENCE'
    : 'U.S. MARKET RISK INTELLIGENCE';

  return (
    <header className="border-b border-dark-border bg-dark-card/80 backdrop-blur sticky top-0 z-50 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center space-x-3">
        <ShieldAlert className="w-6 h-6 text-financial-red animate-pulse" />

        <span className="font-bold text-lg tracking-wider text-white">
          {marketName}
        </span>

        <span className="text-xs px-2 py-0.5 rounded bg-dark-border text-gray-400">
          AI EARLY WARNING SYSTEM
        </span>
      </div>

      <nav className="flex items-center space-x-6 text-sm font-medium">
        <Link
          href={isKorea ? '/korea' : '/'}
          className="flex items-center space-x-2 text-gray-300 hover:text-white transition-colors"
        >
          <Activity className="w-4 h-4 text-financial-blue" />
          <span>PAGE 01 — Market Risk</span>
        </Link>

        <Link
          href={isKorea ? '/korea/validation' : '/validation'}
          className="flex items-center space-x-2 text-gray-300 hover:text-white transition-colors"
        >
          <BarChart3 className="w-4 h-4 text-financial-green" />
          <span>PAGE 02 — Model Validation</span>
        </Link>

        <Link
          href={isKorea ? '/korea/methodology' : '/methodology'}
          className="flex items-center space-x-2 text-gray-300 hover:text-white transition-colors"
        >
          <FlaskConical className="w-4 h-4 text-financial-amber" />
          <span>PAGE 03 — Methodology</span>
        </Link>
      </nav>
    </header>
  );
}
