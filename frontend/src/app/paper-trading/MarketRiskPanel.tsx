'use client';

import Link from 'next/link';
import { createContext, useContext, useEffect, useState, useId, ReactNode } from 'react';
import { LocalizedText } from '../i18n/provider';
import DataHealthNotice from '../components/DataHealthNotice';
import { Latest, Market, fmt, modelAvailable, signal, tone } from '../components/market-data';

const MarketRiskContext = createContext<Record<Market, Latest | null> | null>(null);

// One independent request per market, shared by the status strip and order context.
export function MarketRiskProvider({ children }: { children: ReactNode }) {
  const [snapshots, setSnapshots] = useState<Record<Market, Latest | null>>({ us: null, korea: null });
  useEffect(() => {
    const controller = new AbortController();
    for (const market of ['us', 'korea'] as const) {
      void fetch(market === 'us' ? '/api/latest' : '/api/korea/latest', { signal: controller.signal, cache: 'no-store' })
        .then(response => { if (!response.ok) throw new Error('Market context unavailable'); return response.json(); })
        .then(latest => { if (!controller.signal.aborted) setSnapshots(current => ({ ...current, [market]: latest })); })
        .catch(() => { if (!controller.signal.aborted) setSnapshots(current => ({ ...current, [market]: null })); });
    }
    return () => controller.abort();
  }, []);
  return <MarketRiskContext.Provider value={snapshots}>{children}</MarketRiskContext.Provider>;
}

export function MarketRiskPanel({ market, latest, compact = false }: { market: Market; latest: Latest | null; compact?: boolean }) {
  const status = signal(market, latest);
  const titleId = useId();
  const health = latest?.data_health;
  const freshness = <span className={`command-freshness ${health?.is_current && modelAvailable(latest) ? 'green' : 'amber'}`}><LocalizedText id={health?.status === 'ERROR' ? 'error_data_health' : undefined}>{health?.status || 'UNAVAILABLE'}</LocalizedText></span>;
  return <aside className={`history-panel rw-risk ${compact ? 'rw-risk-compact' : ''}`} aria-labelledby={titleId}>
    <div className="rw-section-heading"><div><div className="eyebrow"><LocalizedText>{market === 'us' ? 'U.S.' : 'Korea'}</LocalizedText></div><h2 id={titleId}><LocalizedText id="rw_market_risk"/></h2></div><span className={`risk-badge ${tone(status)}`}><LocalizedText>{status}</LocalizedText></span></div>
    <div className="command-risk-reading"><div className={`rw-risk-score ${tone(status)}`}><strong>{fmt(modelAvailable(latest) ? latest?.risk_score_10d : null, 1)}</strong><span>/ 100</span></div><p className="rw-risk-horizon"><LocalizedText id="rw_signal_horizon"/></p></div>
    <div className="rw-risk-observation"><span><LocalizedText id="command_observation"/> <time>{latest?.last_updated || '—'}</time></span>{freshness}</div>
    {!compact && <>
      <p className="comparison-note"><LocalizedText id="rw_market_scope"/></p>
      <details className="command-health-details"><summary><LocalizedText id="input_data_health"/></summary><DataHealthNotice market={market} latest={latest}/></details>
      <Link className="rw-text-link" href={market === 'us' ? '/us' : '/korea'}><LocalizedText id="rw_market_details"/><span aria-hidden="true"> ↗</span></Link>
    </>}
  </aside>;
}

export default function CurrentMarketRisk({ market, compact = false }: { market: Market; compact?: boolean }) {
  const shared = useContext(MarketRiskContext);
  const [state, setState] = useState<{ market: Market; latest: Latest | null } | null>(null);
  useEffect(() => {
    if (shared !== null) return;
    const controller = new AbortController();
    const path = market === 'us' ? '/api/latest' : '/api/korea/latest';
    void fetch(path, { signal: controller.signal, cache: 'no-store' }).then(response => {
      if (!response.ok) throw new Error('Market context unavailable');
      return response.json();
    }).then(latest => { if (!controller.signal.aborted) setState({ market, latest }); })
      .catch(() => { if (!controller.signal.aborted) setState({ market, latest: null }); });
    return () => controller.abort();
  }, [market, shared]);
  // Never show the previous market's score while the selected market loads.
  return <MarketRiskPanel compact={compact} market={market} latest={shared !== null ? shared[market] : state?.market === market ? state.latest : null}/>;
}
