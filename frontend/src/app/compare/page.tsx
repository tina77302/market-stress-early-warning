'use client';

import { LocalizedText } from '../i18n/provider';


import { useMemo, useState } from 'react';
import CrossMarketSnapshot, { ModelDisclaimer } from '../components/CrossMarketSnapshot';
import { HistoryChart } from '../components/MarketDetail';
import { normalizeComparison } from '../components/comparison';
import { finite, fmt, HistoryPoint, useMarket } from '../components/market-data';
export default function ComparePage() {
  const us = useMarket('us'), korea = useMarket('korea');
  const [range, setRange] = useState<'1Y' | '3Y' | '5Y' | 'ALL'>('3Y');
  const comparisons = useMemo(() => {
    const sharedEnd = us.history.length && korea.history.length ? [us.history[us.history.length - 1].date, korea.history[korea.history.length - 1].date].sort()[0] : null;
    const start = sharedEnd ? new Date(sharedEnd) : null;
    if (start && range !== 'ALL') start.setFullYear(start.getFullYear() - Number(range[0]));
    const filter = (rows: HistoryPoint[]) => rows.filter(row => sharedEnd && row.date <= sharedEnd && (range === 'ALL' || (start && new Date(row.date) >= start)));
    const a = filter(us.history), b = filter(korea.history);
    return [
      { title: 'MARKET STRESS COMPARISON', description: 'MSI relative to each market’s own distribution.', result: normalizeComparison(a, b, 'msi', 'msi') },
      { title: 'VOLATILITY', description: 'VIX and VKOSPI relative to their own histories. Raw index levels have different market definitions and scales.', result: normalizeComparison(a, b, 'vix', 'vkospi') },
      { title: 'CREDIT CONDITIONS', description: 'Baa–Treasury and Korean AA− Corporate − Government 3Y spreads relative to their own histories. Instruments and tenors differ.', result: normalizeComparison(a, b, 'baa_treasury_spread', 'korea_credit_spread_bp') },
    ];
  }, [us.history, korea.history, range]);
  const stress = comparisons[0].result;
  const together = finite(stress.changeUS) && finite(stress.changeKorea) ? stress.changeUS === 0 || stress.changeKorea === 0 ? 'At least one series was unchanged' : Math.sign(stress.changeUS) === Math.sign(stress.changeKorea) ? 'Both stress indicators moved in the same direction' : 'Stress indicators moved in opposite directions' : null;
  return <div className="risk-home detail-page"><div className="home-content"><section className="detail-heading"><div className="eyebrow"><LocalizedText id="cross_market_overview_dd3678"/></div><h1><LocalizedText id="two_markets_independent_signals_3b699e"/></h1><p><LocalizedText id="monitor_u_s_and_korea_financial_stress_in_context_fa4248"/></p></section>
    {(us.loading || korea.loading) && <div className="api-notice" role="status"><LocalizedText id="loading_cross_market_observations_0b2557"/></div>}
    {[{ name: 'U.S.', state: us }, { name: 'Korea', state: korea }].map(({ name, state }) => !!state.errors.length && <div key={name} className="api-notice" role="status"><LocalizedText>{name}</LocalizedText>: <LocalizedText>{state.errors.join(', ')}</LocalizedText><LocalizedText id="unavailable_9cd983" before after/><button disabled={state.loading} onClick={state.retry}><LocalizedText id="retry_9f5cd8" after/><LocalizedText>{name}</LocalizedText></button></div>)}
    <CrossMarketSnapshot us={us.latest} korea={korea.latest}/>
    <div className="chart-heading detail-range"><h2><LocalizedText id="historical_cross_market_monitoring_82d309"/></h2><div className="range-buttons">{(['1Y', '3Y', '5Y', 'ALL'] as const).map(value => <button key={value} onClick={() => setRange(value)} aria-pressed={range === value} className={range === value ? 'selected' : ''}><LocalizedText>{value}</LocalizedText></button>)}</div></div>
    <p className="comparison-note"><LocalizedText id="within_market_z_score_value_market_mean_market_standard_deviation_4c9dae"/></p>
    {comparisons.map(({ title, description, result }) => <section className="history-panel" key={title}><h2><LocalizedText>{title}</LocalizedText></h2><p className="comparison-note"><LocalizedText>{description}</LocalizedText></p><div className="chart-legend"><span><i/><LocalizedText id="u_s_z_score_84eb87"/></span><span><i/><LocalizedText id="korea_z_score_e6bbd3"/></span></div><div className="history-chart"><HistoryChart sharedScale data={result.data} fields={[{ key: 'us', label: 'U.S. z-score', color: '#47e1bf' }, { key: 'korea', label: 'Korea z-score', color: '#eab451' }]}/></div><p className="comparison-note"><LocalizedText>{result.data.length ? `${result.start} – ${result.end} · ${result.count} matched observations · normalized within each market.` : `Comparison unavailable: requires at least 20 matched finite observations and nonzero variance in both markets (${result.count} matched).`}</LocalizedText></p></section>)}
    <section className="history-panel assessment"><h2><LocalizedText id="divergence_co_movement_73646b"/></h2><p><LocalizedText>{together ? `${together} over the last 20 shared observation intervals ending ${stress.end}. U.S. MSI change: ${fmt(stress.changeUS, 2)} z; Korea: ${fmt(stress.changeKorea, 2)} z.` : 'Recent movement comparison unavailable: at least 21 shared MSI observations are needed.'}</LocalizedText></p><p><LocalizedText>{finite(stress.correlation) ? `Descriptive Pearson correlation of MSI levels over ${stress.count} matched observations (${stress.start} – ${stress.end}): ${fmt(stress.correlation, 2)}.` : 'Descriptive MSI correlation unavailable.'}</LocalizedText><LocalizedText id="same_date_observations_reflect_different_market_closing_times_lev_b18f2b" before/></p></section><ModelDisclaimer/>
  </div></div>;
}
