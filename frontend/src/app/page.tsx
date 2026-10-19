'use client';
import { LocalizedText } from './i18n/provider';
import { useMarket } from './components/market-data';
import { CommandMarketCard, GlobalHero } from './components/GlobalCommand';
export default function Overview() {
 const us=useMarket('us'),korea=useMarket('korea');
 return <div className="risk-home overview-console mc mc-global-command"><GlobalHero us={us.latest} korea={korea.latest}/>
  <section className="mc-command-markets" aria-label="Market monitoring consoles"><CommandMarketCard market="us" latest={us.latest} history={us.history}/><CommandMarketCard market="korea" latest={korea.latest} history={korea.history}/></section>
  <footer className="mc-footer"><LocalizedText>{'Independent markets. Separate observations, thresholds and provenance. Historical observations are not LIVE forecasts.'}</LocalizedText><a href="/monitoring/credits.html"><LocalizedText>{'Visual credits'}</LocalizedText></a></footer>
 </div>;
}
