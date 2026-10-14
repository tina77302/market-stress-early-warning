'use client';
import { LocalizedText } from '../i18n/provider';
import { Latest, Market } from './market-data';
export default function DataHealthNotice({market,latest}:{market:Market;latest:Latest|null}) {
  const health=latest?.data_health;
  if (health?.is_current) return <aside className="data-health-notice data-health-current" role="status"><strong><LocalizedText>{market==='us'?'U.S.':'Korea'}</LocalizedText> · <LocalizedText id={health.status==='ERROR'?'error_data_health':undefined}>{health.status}</LocalizedText></strong><span><LocalizedText id="data_through"/>: {latest?.last_updated || '—'}</span></aside>;
  return <aside className="data-health-notice" role="status"><strong><LocalizedText>{market==='us'?'U.S.':'Korea'}</LocalizedText> · <LocalizedText id={health?.status==='ERROR'?'error_data_health':undefined}>{health?.status || 'UNAVAILABLE'}</LocalizedText></strong><span><LocalizedText id="current_risk_unavailable_health"/> <LocalizedText>{latest?.last_updated ? `Last validated observation: ${latest.last_updated}` : 'No validated snapshot.'}</LocalizedText></span><details><summary><LocalizedText id="input_data_health"/></summary><ul>{health?.input_series.map(input=><li key={input.series}><span><LocalizedText>{input.series}</LocalizedText></span><span><LocalizedText id={input.status==='ERROR'?'error_data_health':undefined}>{input.status}</LocalizedText> · <LocalizedText>{input.latest_observation_date || 'Unavailable'}</LocalizedText></span></li>)}</ul></details></aside>;
}
