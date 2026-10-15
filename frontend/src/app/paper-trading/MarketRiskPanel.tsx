'use client';

import Link from 'next/link';
import { useEffect, useState, useId } from 'react';
import { LocalizedText } from '../i18n/provider';
import DataHealthNotice from '../components/DataHealthNotice';
import { Latest, Market, fmt, modelAvailable, signal, tone } from '../components/market-data';

export function MarketRiskPanel({ market, latest, compact = false }: { market: Market; latest: Latest | null; compact?: boolean }) {
  const status = signal(market, latest);
  const titleId = useId();
  return <aside className={`history-panel rw-risk ${compact ? 'rw-risk-compact' : ''}`} aria-labelledby={titleId}>
    <div className="rw-section-heading"><div><div className="eyebrow"><LocalizedText>{market === 'us' ? 'U.S.' : 'Korea'}</LocalizedText></div><h2 id={titleId}><LocalizedText id="rw_market_risk"/></h2></div><span className="rw-tag"><LocalizedText id="rw_market_level"/></span></div>
    <div className={`rw-risk-score ${tone(status)}`}><strong>{fmt(modelAvailable(latest) ? latest?.risk_score_10d : null, 1)}</strong><span>/ 100</span></div>
    <span className={`risk-badge ${tone(status)}`}><LocalizedText>{status}</LocalizedText></span>
    <p className="rw-risk-horizon"><LocalizedText id="rw_signal_horizon"/></p>
    <div className="rw-risk-observation"><LocalizedText id="command_observation"/> {latest?.last_updated || '—'}</div>
    <DataHealthNotice market={market} latest={latest}/>
    {!compact && <p className="comparison-note"><LocalizedText id="rw_market_scope"/></p>}
    {!compact && <Link className="rw-text-link" href={market === 'us' ? '/us' : '/korea'}><LocalizedText id="rw_market_details"/><span aria-hidden="true"> ↗</span></Link>}
  </aside>;
}

export default function CurrentMarketRisk({ market, compact = false }: { market: Market; compact?: boolean }) {
  const [state, setState] = useState<{ market: Market; latest: Latest | null } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const path = market === 'us' ? '/api/latest' : '/api/korea/latest';
    void fetch(path, { signal: controller.signal, cache: 'no-store' }).then(response => {
      if (!response.ok) throw new Error('Market context unavailable');
      return response.json();
    }).then(latest => { if (!controller.signal.aborted) setState({ market, latest }); })
      .catch(() => { if (!controller.signal.aborted) setState({ market, latest: null }); });
    return () => controller.abort();
  }, [market]);
  // Never show the previous market's score while the selected market loads.
  return <MarketRiskPanel compact={compact} market={market} latest={state?.market === market ? state.latest : null}/>;
}
