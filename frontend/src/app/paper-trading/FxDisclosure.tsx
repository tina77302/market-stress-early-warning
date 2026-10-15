import { LocalizedText } from '../i18n/provider';
import { FxObservation } from './types';

export const isExchangeRate = (source?:string) => source === 'exchangerate.dev Free / USD/KRW (15-minute delayed)';

export function FxAttribution({source}:{source?:string}) {
  if(isExchangeRate(source))return <a className="rw-text-link" href="https://exchangerate.dev" target="_blank" rel="noreferrer">{'Rates by Exchangerate.dev'}</a>;
  if(source==='Twelve Data / USD/KRW')return <a className="rw-text-link" href="https://twelvedata.com/"><LocalizedText id="fx_provider_attribution"/></a>;
  return null;
}

export function FxDelay({fx}:{fx?:FxObservation|null}) {
  if(!isExchangeRate(fx?.source))return null;
  return <p className="comparison-note"><LocalizedText id="fx_exchange_delayed"/></p>;
}
