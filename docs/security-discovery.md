# Paper Trading security discovery

## Audit and architecture

The previous `prices.SECURITIES` constant contained seven instruments. Both the
server's `/api/paper/securities` handler and `prices.security()` used that list;
quote and order endpoints rejected anything outside it. The browser downloaded
it and filtered a select element locally. Roles never changed the universe.
Yahoo/yfinance already supplied completed daily closes, with currency and price
freshness checks. ETFs were entries in the same small list.

The replacement is:

structured listing files -> separate persistent symbol master -> bounded server
search -> selected execution key -> verified provider identity/quote -> existing
Paper Trading execution engine.

No account-schema migration is required. `src/paper/service.py` accounting,
initial balances, ownership, CSRF/auth/session code, model files, market data,
MSI/SHAP, model thresholds and the market refresh scheduler are unchanged.

## Sources and supported subset

- U.S.: Nasdaq Trader `nasdaqlisted.txt` and `otherlisted.txt`, via HTTPS.
  [Official field definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs).
  Covers supported Nasdaq, NYSE, NYSE American, NYSE Arca and Cboe BZX entries.
  Common/ordinary/capital-stock name classifications and explicit ETF flags are
  used conservatively. Test issues, NextShares, non-normal Nasdaq financial
  statuses and unsupported symbol formats are not tradable. Preferred,
  depositary, warrant, right, unit, note and recognized leveraged/inverse name
  markers are excluded. ADRs, OTC, options, futures, mutual funds, bonds, ETNs,
  IEX and ambiguous types are outside this implementation. Name screening is
  conservative, not a guarantee of any fund's investment strategy or risk.
- Korea: KIS public `kospi_code.mst.zip` and `kosdaq_code.mst.zip` files, using
  [KIS's documented layouts](https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info).
  CP949 fixed-width records supply KOSPI/KOSDAQ names, group types, preferred
  flags, suspension and liquidation flags. Common `ST` and ETF `EF` groups are
  supported; preferred flags other than zero, other groups, suspensions,
  liquidation and recognized leveraged/inverse names are excluded from trading.
  KONEX, preferred shares, ETNs, rights, warrants and other master groups are not
  supported. Current source data contains KOSPI ETFs, not KOSDAQ ETFs.
  KRX structured APIs were investigated; this implementation does not require
  additional KRX API approval or a broker account/key. It does not scrape HTML.

A real source refresh was verified in a separate `/tmp` database. For the files
with Nasdaq creation time 2026-10-14 21:31 America/New_York and KIS Last-Modified
2026-10-15 01:55:03 UTC, the parser yielded these **search-eligible** counts:

| Exchange | Stocks | ETFs |
| --- | ---: | ---: |
| Nasdaq | 2,897 | 1,089 |
| NYSE | 1,908 | 79 |
| NYSE American | 253 | 0 |
| NYSE Arca | 0 | 2,456 |
| Cboe BZX | 1 | 1,286 |
| KOSPI | 776 | 774 |
| KOSDAQ | 1,654 | 0 |

These are snapshot observations, not guarantees of current availability or
Yahoo quote support. Each quote still requires validation. No listing dataset
or price history is committed to the repository.

## Persistence, refresh and failure behavior

The master defaults to `/app/data/paper/security-master.sqlite3` in staging,
therefore `/srv/market-stress/data/paper/security-master.sqlite3` on the existing
bind mount. It is separate from `workspace.sqlite3`. `PAPER_SYMBOL_MASTER_PATH`
is an optional process-level override, used by isolated tests.

A per-market filesystem lock serializes refreshes across processes. Downloads
have connect/read timeouts, compressed/uncompressed size limits, and normal TLS
verification. Each market's complete directory and public-source SHA-256 /
source timestamps commit in one SQLite transaction. Missing/truncated sources,
conflicting duplicate identities, fewer than 1,000 supported records or an
unexpected >30% shrink preserve the prior directory. Identical duplicates are
collapsed. Only metadata is stored; no prices/history are imported.

Search lazily refreshes a missing/day-old directory with a 60-second failure
cooldown. Cached search metadata may be shown for up to three days with a STALE
notice. **Trading requires a directory refreshed within 24 hours**, as well as
the unchanged quote-freshness rules. Refresh failure never creates fabricated
listings/prices. A missing/expired directory returns 503; unknown/inactive or
wrong-market instruments return 422. Markets refresh independently.

A separate trusted CLI can prewarm/refresh the master without starting another
market scheduler:

```bash
sudo docker compose --env-file /etc/market-stress/staging.env \
  -f deploy/docker-compose.staging.yml exec -T api \
  python -m src.paper.symbol_master refresh --market both

sudo docker compose --env-file /etc/market-stress/staging.env \
  -f deploy/docker-compose.staging.yml exec -T api \
  python -m src.paper.symbol_master status --market both
```

No deployment or schedule installation is performed by this change. A regular
operator refresh can avoid the first-search download delay; the existing model
scheduler is neither changed nor reused. The Dockerfile already copies all of
`src/paper`; no new runtime dependency is required. Rebuild API and frontend
images when deploying the code.

## API, identity and search

The existing authenticated endpoint is adapted, not duplicated:

`GET /api/paper/securities?market=us|korea&q=...&limit=20`

The public frontend continues using `/api/workspace/paper/securities`. Existing
`symbol`, `name`, `market`, `currency` fields are retained; `ticker`, `exchange`,
`security_type` and directory status/time are added. Default result limit is 20,
maximum 30; empty queries return no universe. Queries are at most 100 characters;
control characters are rejected. SQL wildcards are treated literally.

Ranking is exact ticker/execution key, ticker prefix, exact normalized name,
name prefix, then substring; ties use ticker length and alphabetical order.
Unicode normalization, case folding and punctuation/space removal support
Korean names and variations. Single-character queries return only exact tickers.

When local search has no hits, bounded `yf.Search()` may resolve alternate names
(e.g. English Korean-company names). Results are cached for five minutes with
at most 256 query keys and two concurrent lookups, using a four-second timeout.
News/recommendation results are not used. Returned names must match the query;
only matching type/provider symbols already in the correct market master can
be returned. Yahoo never adds an unlisted instrument to the trading universe.
See [yfinance Search documentation](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Search.html).

For Korean holdings, `symbol` remains the existing `.KS` / `.KQ` execution key,
so existing portfolios, pending orders and history retain their identity. The
`ticker` field is the six-digit exchange code shown in the picker, positions
and activity. Quotes/orders accept a six-digit code and normalize it to the
stored key. Nasdaq/NYSE class symbols retain their exchange code and map dots
to Yahoo hyphens only at the provider boundary. No account data is rewritten.

## Quote/order validation and UI

The selected record determines the provider symbol; user text is never sent
straight to the quote provider. Yahoo history metadata must agree on symbol,
exchange, currency and EQUITY/ETF type. Existing completed-close selection,
minor-unit rounding, maximum price age and two-minute quote expiry are retained.
Validated completed-close prices have a bounded 15-second, 256-entry process
cache; cache hits recheck price freshness and listing eligibility. Quote IDs
remain independently bound to each user, market and execution symbol.

The same order engine still enforces cash, quantity, position, quote ownership,
CSRF and idempotency. Both roles use the same directory/search and validation.
No admin-only expansion, FX, borrowing, short selling or recommendations exist.

The picker debounces queries for 300 ms, aborts stale responses, caps results,
shows ticker/name/exchange/market/type, and supports arrows/Enter/Escape. Enter
on unselected free text cannot load a quote. Editing the query clears selection
and quote; review/submission disables discovery. A selected listing is explicitly
not a validated quote. Existing market-risk context stays separate from
security pricing and is not described as a stock-return prediction.

## Data terms and operational limits

Free technical access does **not** establish unrestricted commercial/public
redistribution rights. Review Nasdaq directory terms and KIS master-data use
conditions for the intended audience; the KIS repository's code license does
not establish rights to redistribute its downloaded metadata. The public KIS
master does not supply comprehensive English company names or a source timestamp
inside each record; HTTP Last-Modified is retained when present.

[yfinance's own notice](https://github.com/ranaroussi/yfinance#readme) states that
it is not affiliated with Yahoo, is intended for research/education, and points
to personal-use limits and Yahoo's data terms. Yahoo may throttle or change its
unofficial interfaces; listings do not guarantee reliable quotes. No exchange-
authoritative real-time service, complete-universe support, or commercial data
license is claimed. Existing simulated-trading disclaimers remain visible.

Automated tests use fixture master data and mock provider boundaries. No live
browser/keyboard/mobile interaction or end-to-end live Yahoo trade was tested.
