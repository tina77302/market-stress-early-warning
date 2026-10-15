import { ApiError, Market, Portfolio, Quote, Security, workspace } from './types';

const normalize = (text: string) => text.normalize('NFKC').toLowerCase().replace(/\s+/g, '');
export function rankSecurities(items: Security[], query: string, limit = 20) {
  const key = normalize(query);
  if (!key) return [];
  const rank = (item: Security) => {
    const ticker = normalize(item.ticker), name = normalize(item.name);
    return ticker === key ? 0 : ticker.startsWith(key) ? 1 : name === key ? 2 : name.startsWith(key) ? 3 : 4;
  };
  const unique = new Map<string, Security>();
  for (const item of items) unique.set(`${item.market}:${item.symbol}`, item);
  return Array.from(unique.values()).sort((a,b) => rank(a)-rank(b) || a.ticker.localeCompare(b.ticker) || a.market.localeCompare(b.market)).slice(0,limit);
}

export async function searchSecurities(query: string, market: Market | 'all', signal: AbortSignal) {
  if (!query.trim()) return { data: [], stale: false, partial: false };
  const markets: Market[] = market === 'all' ? ['us','korea'] : [market];
  const results = await Promise.allSettled(markets.map(book => workspace<{data: Security[]; directory_status?: string}>(`paper/securities?market=${book}&q=${encodeURIComponent(query.trim())}&limit=30`, {signal})));
  if (signal.aborted) throw new DOMException('Search cancelled','AbortError');
  const good = results.flatMap(result => result.status === 'fulfilled' ? [result.value] : []);
  if (!good.length) throw new Error('Security search is temporarily unavailable. Try again.');
  return { data: rankSecurities(good.flatMap(result=>result.data),query), stale: good.some(result=>result.directory_status==='STALE'), partial: good.length !== markets.length };
}

export function settlementPortfolio(market: Market, portfolios?: Partial<Record<Market, Portfolio | null>>, fallback?: Portfolio | null) {
  const book = portfolios ? portfolios[market] : fallback;
  return book?.market === market && book.currency === (market==='us'?'USD':'KRW') ? book : null;
}

export async function selectedQuote(security: Pick<Security,'market'|'symbol'|'currency'>, signal: AbortSignal): Promise<Quote> {
  const quote = await workspace<Quote>(`paper/quote?market=${security.market}&symbol=${encodeURIComponent(security.symbol)}`,{signal});
  if (signal.aborted) throw new DOMException('Quote cancelled','AbortError');
  if (quote.market!==security.market || quote.symbol!==security.symbol || quote.currency!==security.currency ||
      quote.currency!==(security.market==='us'?'USD':'KRW') || !Number.isFinite(quote.price) || quote.price<=0 ||
      !Number.isFinite(Date.parse(quote.observed_at)) || !Number.isFinite(quote.expires_at) || quote.expires_at*1000<=Date.now()) {
    throw new Error('Quote expired or unusable. Refresh the quote before reviewing.');
  }
  return quote;
}

export function estimatedOrder(quote: Quote | null, quantity: string) {
  const units = Number(quantity);
  return quote && /^\d+$/.test(quantity) && Number.isSafeInteger(units) && units>0 && units<=1000000 ? quote.price*units : null;
}

export function quoteFailure(error: unknown) {
  if(error instanceof Error && error.message==='Quote expired or unusable. Refresh the quote before reviewing.') return error.message;
  if(error instanceof ApiError && error.message.includes('sufficiently recent valid completed close')) return 'A sufficiently recent validated close is unavailable. This security cannot be traded until a usable quote is available.';
  return 'Price data is temporarily unavailable for this security. Refresh the quote to retry.';
}
