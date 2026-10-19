'use client';

import { LocalizedText } from '../i18n/provider';
import Link from 'next/link';
import DataHealthNotice from './DataHealthNotice';
import { fmt, Latest, modelAvailable, signal } from './market-data';
export function ModelDisclaimer() {
  return <p className="model-disclaimer"><LocalizedText id="model_outputs_are_decision_support_signals_not_investment_recomme_227c51"/></p>;
}
export default function CrossMarketSnapshot({ us, korea }: { us: Latest | null; korea: Latest | null }) {
  const rows = [
    ['10D Model Score', fmt(modelAvailable(us) ? us?.risk_score_10d : null, 1, ' / 100'), fmt(modelAvailable(korea) ? korea?.risk_score_10d : null, 1, ' / 100')],
    ['Existing Model Classification', signal('us', us) === 'BELOW WARNING' ? 'Operational warning not triggered' : signal('us', us), signal('korea', korea) === 'BELOW WARNING' ? 'Operational warning not triggered' : signal('korea', korea)],
    ['Operational Warning', typeof us?.warning_active === 'boolean' ? us.warning_active ? 'WARNING' : 'Operational warning not triggered' : 'Operational warning state unavailable', typeof korea?.warning_active === 'boolean' ? korea.warning_active ? 'WARNING' : 'Operational warning not triggered' : 'Operational warning state unavailable'],
    ['Stress Event threshold', fmt(us?.stress_threshold, 3), fmt(korea?.stress_threshold, 3)],
    ['Current Stress Event', typeof us?.is_stress_event === 'boolean' ? us.is_stress_event ? 'YES' : 'Stress Event threshold not reached' : 'Stress Event state unavailable', typeof korea?.is_stress_event === 'boolean' ? korea.is_stress_event ? 'YES' : 'Stress Event threshold not reached' : 'Stress Event state unavailable'],
    ['Stress Index / MSI', fmt(modelAvailable(us) ? us?.market_stress_index : null, 3), fmt(modelAvailable(korea) ? korea?.market_stress_index : null, 3)],
    ['Equity', `SPY · ${fmt(us?.spy_price, 2, ' USD')}`, `KOSPI200 · ${fmt(korea?.kospi200)}`],
    ['Volatility', `VIX · ${fmt(us?.vix_level)}`, `VKOSPI · ${fmt(korea?.vkospi)}`],
    ['Credit', `Baa–Treasury · ${fmt(us?.baa_treasury_spread, 3, ' percentage points')}`, `AA− Corp–Govt 3Y · ${fmt(korea?.korea_credit_spread_bp, 1, ' bp')}`],
    ['Deployment Model', 'XGBoost', 'XGBoost'], ['Forecast Horizon', '10 Trading Days', '10 Trading Days'],
    ['Last Observation', us?.last_updated || '—', korea?.last_updated || '—'],
    ['Data Status', us?.data_health?.status || 'UNAVAILABLE', korea?.data_health?.status || 'UNAVAILABLE'],
  ];
  return <section className="history-panel cross-snapshot"><DataHealthNotice market="us" latest={us}/><DataHealthNotice market="korea" latest={korea}/><div className="chart-heading"><h2><LocalizedText id="cross_market_snapshot_4cfe53"/></h2><Link href="/compare"><LocalizedText id="explore_comparison_ff1e36"/></Link></div><div className="table-scroll"><table><thead><tr><th scope="col"><LocalizedText id="metric_b2bb76"/></th><th scope="col"><LocalizedText id="u_s_7a3239"/></th><th scope="col"><LocalizedText id="korea_4e8bd0"/></th></tr></thead><tbody>{rows.map(([label, a, b]) => <tr key={label}><th scope="row"><LocalizedText>{label}</LocalizedText></th><td><LocalizedText id={label==='Data Status' && a==='ERROR'?'error_data_health':undefined}>{a}</LocalizedText></td><td><LocalizedText id={label==='Data Status' && b==='ERROR'?'error_data_health':undefined}>{b}</LocalizedText></td></tr>)}</tbody></table></div><p className="comparison-note"><LocalizedText id="scores_are_market_specific_model_outputs_and_should_not_be_interp_f61395"/></p></section>;
}
export function GlobalAssessment({ us, korea }: { us: Latest | null; korea: Latest | null }) {
  const a = signal('us', us), b = signal('korea', korea);
  const summary = a === 'UNAVAILABLE' || b === 'UNAVAILABLE' ? 'A complete cross-market assessment is unavailable because one or more current model signals are missing.' : a === 'WARNING' || b === 'WARNING' ? 'An operational warning is active in at least one market.' : 'Operational warnings are not triggered. Scores below 50 do not rule out market shocks.';
  return <section className="history-panel assessment"><h2><LocalizedText id="global_market_assessment_af76f3"/></h2><p><LocalizedText>{summary}</LocalizedText></p><div className="assessment-grid"><p><strong><LocalizedText id="u_s_7a3239"/></strong> <LocalizedText>{a}</LocalizedText><LocalizedText id="score_a45ad8" before after/><LocalizedText>{fmt(modelAvailable(us) ? us?.risk_score_10d : null, 1, ' / 100')}</LocalizedText><LocalizedText id="msi_5ce70c" before after/><LocalizedText>{fmt(modelAvailable(us) ? us?.market_stress_index : null, 3)}</LocalizedText>.</p><p><strong><LocalizedText id="korea_4e8bd0"/></strong> <LocalizedText>{b}</LocalizedText><LocalizedText id="score_a45ad8" before after/><LocalizedText>{fmt(modelAvailable(korea) ? korea?.risk_score_10d : null, 1, ' / 100')}</LocalizedText><LocalizedText id="msi_5ce70c" before after/><LocalizedText>{fmt(modelAvailable(korea) ? korea?.market_stress_index : null, 3)}</LocalizedText><LocalizedText id="fixed_warning_reference_50_100_22eda8"/></p></div><p><strong><LocalizedText id="cross_market_view_a423b9"/></strong><LocalizedText id="independent_models_describe_each_market_against_its_own_definitio_af34c2" before/></p></section>;
}
