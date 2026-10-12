'use client';
import { LocalizedText } from '../i18n/provider';
import { Latest, Market } from './market-data';
export default function DataHealthNotice({market,latest}:{market:Market;latest:Latest|null}) {
  const health=latest?.data_health;
  if (health?.is_current) return null;
  return <aside className="data-health-notice" role="status"><strong><LocalizedText>{market==='us'?'U.S.':'Korea'}</LocalizedText> · <LocalizedText>{health?.status || 'UNAVAILABLE'}</LocalizedText></strong><span><LocalizedText id="current_risk_unavailable_health"/> <LocalizedText>{latest?.last_updated ? `Last validated observation: ${latest.last_updated}` : 'No validated snapshot.'}</LocalizedText></span><details><summary><LocalizedText id="input_data_health"/></summary><ul>{health?.input_series.map(input=><li key={input.series}><span>{input.series}</span><span><LocalizedText>{input.status}</LocalizedText> · <LocalizedText>{input.latest_observation_date || 'Unavailable'}</LocalizedText></span></li>)}</ul></details></aside>;
}
