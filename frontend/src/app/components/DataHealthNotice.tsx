'use client';
import { LocalizedText } from '../i18n/provider';
import { Latest, Market, modelAvailable } from './market-data';
export default function DataHealthNotice({market,latest}:{market:Market;latest:Latest|null}) {
  const health=latest?.data_health;
  const available=modelAvailable(latest);
  if (health?.is_current && available) return <aside className="data-health-notice data-health-current" role="status"><strong><LocalizedText>{market==='us'?'U.S.':'Korea'}</LocalizedText> · <LocalizedText>{health.status}</LocalizedText></strong><span><LocalizedText id="data_through"/>: {latest?.last_updated || '—'}</span></aside>;
  const message = !available ? 'current_risk_unavailable_health' : health?.status==='DELAYED' ? 'freshness_delayed_notice' : health?.status==='ERROR' ? 'freshness_error_notice' : health?.status==='PARTIAL' ? 'freshness_partial_notice' : 'freshness_stale_notice';
  return <aside className="data-health-notice" role="status"><strong><LocalizedText>{market==='us'?'U.S.':'Korea'}</LocalizedText> · <LocalizedText id={health?.status==='ERROR'?'error_data_health':undefined}>{health?.status || 'UNAVAILABLE'}</LocalizedText></strong><span><LocalizedText id={message}/> <LocalizedText>{latest?.last_updated ? `Last validated observation: ${latest.last_updated}` : 'No validated snapshot.'}</LocalizedText></span><details><summary><LocalizedText id="input_data_health"/></summary><ul>{health?.input_series.map(input=><li key={input.series}><span><LocalizedText>{input.series}</LocalizedText></span><span><LocalizedText id={input.status==='ERROR'?'error_data_health':undefined}>{input.status}</LocalizedText> · <LocalizedText>{input.latest_observation_date || 'Unavailable'}</LocalizedText></span></li>)}</ul></details></aside>;
}
