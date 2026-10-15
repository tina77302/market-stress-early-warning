# Reviewed real-data evidence: first local research coverage

No UI redesign, model training, calibration, threshold changes, or account reset.
The existing deterministic analytics and authenticated endpoint remain in use.
This is a small source-reviewed research universe, not a complete listing universe
or a certification of historical constituent membership.

## Inspection and external inputs

The existing project has U.S./Korea OOS model outputs, market-index prices,
exchange calendars, canonical listing identities, and unified accounting. It has
no security classifications or adjusted sector/security histories. Those are the
only new external inputs needed. Reuse the existing Nasdaq/KIS listing refresh;
do not create another symbol directory. The first local refresh populated those
existing directories; it did not change discovery APIs or trading rules.

| Input | Selected source | Scope and limit |
|---|---|---|
| Security identity | Existing Nasdaq Trader and KIS Symbol Master | Canonical keys and provider symbols remain unchanged; listing, currency, venue and instrument type must match. |
| U.S. and Korean stock classification | Yahoo Finance structured company metadata | Copy the reported `sector` and `industry`, verify identity, and require exact agreement with the reviewed catalog. No company-name inference. |
| Adjusted histories | Existing yfinance dependency, explicit Yahoo `Adj Close` | Split/dividend-adjusted daily provider prices; no repaired, interpolated, unadjusted or synthetic substitutes. |
| U.S. sector benchmark | [XLK issuer](https://www.ssga.com/us/en/individual/etfs/state-street-technology-select-sector-spdr-etf-xlk) | Technology Select Sector Index mandate; proxy evidence, not NVIDIA-specific behavior. |
| U.S. industry benchmark | [SOXX issuer](https://www.ishares.com/us/products/239705/ishares-phlx-semiconductor-etf?qt=SOXX) | Semiconductor-industry ETF, not the whole technology sector. |
| Korea sector benchmark | [KODEX IT issuer factsheet](https://m.samsungfund.com/sheet/20220607/2ETF82_20220531.pdf) | 266370, KRX IT mandate, including SK hynix in the dated holdings. Document as of 2022-05-31, not a claim about current constituent weights. |
| Korea industry benchmark | [KODEX semiconductor issuer factsheet](https://m.samsungfund.com/sheet/20211213/2ETF07_20211130.pdf) | 091160, KRX Semiconductors mandate. Historical factsheet and current issuer product reference are retained in the catalog; not a broad-technology proxy. |

Other sources reviewed but not activated: [SEC submissions](https://www.sec.gov/about/developer-resources)
provide official SIC industry metadata, which is not a complete GICS sector/industry
mapping; do not invent a crosswalk. [OpenDART](https://opendart.fss.or.kr/index.do)
and the [KRX marketplace](https://data.krx.co.kr/) are official Korean alternatives,
but require source-specific identity, taxonomy, access and data-use review. No new
key, paid subscription or licensed GICS dataset was obtained.

### Usage rights are a deployment limitation

[yfinance's official notice](https://ranaroussi.github.io/yfinance/) describes
research/educational use and Yahoo API personal use. Non-commercial status alone
is **not** proof of permission for a public multi-user dashboard, raw redistribution,
or all derived-data uses. This implementation installs private local research
receipts and demonstrates the real computation path; it does not certify public
display/redistribution rights. `public_display_rights=not_confirmed` is preserved in
provenance. Keep these bundles out of Git and deployment artifacts until suitable
permission or a licensed substitute is established. No AWS dataset was installed.

The issuer documents establish factual mandates and reviewed proxy relationships;
they do not grant a general redistribution license for their full documents,
index data or underlying commercial classification systems. Current provider
labels `Technology` / `Semiconductors` are identified as provider taxonomy, not a
licensed point-in-time GICS database. The issuer's Information Technology/정보기술
mandate is an explicitly reviewed display-label alias for Technology. U.S. and
Korean instruments, observations, regimes and statistics remain separate.

## Installed coverage

All prices end on **2026-10-14**; the collection conservatively excludes the current
local market date even if the exchange has already closed.

| Market | Instrument | Evidence kind | First valid date | Valid prices | Missing provider rows |
|---|---|---|---|---:|---:|
| U.S. | NVDA | Security | 2006-01-03 | 5,228 | 0 |
| U.S. | XLK | Sector proxy | 2006-01-03 | 5,228 | 0 |
| U.S. | SOXX | Industry benchmark | 2006-01-03 | 5,228 | 0 |
| Korea | 000660.KS | Security | 2006-01-02 | 5,129 | 1 |
| Korea | 266370.KS | Sector proxy | 2017-03-28 | 2,305 | 29 |
| Korea | 091160.KS | Industry benchmark | 2007-01-29 | 4,280 | 583 |

Missing prices stay absent. The existing full-session check excludes affected
10-session windows, rather than filling gaps or inflating counts. ETF inception
limits and vendor gaps explain different sample counts. No pre-inception index
history is spliced onto an ETF.

The reviewed catalog is `src/paper/stress_coverage.json`. Each stock requires an
exact provider sector/industry match on refresh. Missing or changed classification
fails collection for that market, preserving its last installed bundle. ETF
classification describes a reviewed mandate/proxy, not full look-through sector
weights. The holdings response exposes this distinction as `exposure_basis` and
also carries classification basis and retrieval time. No underlying ETF holdings
allocation is invented.

## Price and provenance validation

The collector reuses the existing canonical provider symbols and checks returned
symbol, currency, venue, security type and exchange timezone. It requests
`auto_adjust=False`, `repair=False`, actions and missing rows explicitly, then
uses only the provider's `Adj Close`. See [Yahoo's adjustment definition](https://in.help.yahoo.com/kb/adjusted-close-sln28256.html).
Yahoo's ordinary Close is already split-adjusted; splits are not applied a second
time. Dividend adjustment factors are checked against reported cash actions.
The first scope requires observable dividend records and at least 252 valid bars;
these are collection-quality requirements, not relaxed statistical thresholds.

Additional issuer spot checks include NVIDIA's [10-for-1 split on June 10, 2024](https://investor.nvidia.com/files/doc_downloads/2024/05/NVIDIA-2024-Stock-Split-FAQ.pdf)
and KODEX IT's 140-won distribution. Its issuer record date is April 29, 2022;
the provider ex-date is April 28. Those are distinct dates and are never relabelled.
Mechanical checks and spot checks do not independently certify every vendor
corporate action. KODEX semiconductor has one cash-action check unavailable due
to an adjacent missing price; that missingness is retained and affected outcome
windows are excluded.

Every generated record carries source URLs, canonical/provider identity,
retrieval/review timestamps, review status and scope, requested cutoff, actual
coverage, adjustment audit and SHA-256 receipt references. Receipts retain the
reviewed catalog, selected provider identity/classification metadata, and original
CSV history. They live under ignored `data/paper/stress-evidence/receipts/`.

The existing importer verifies those receipts and recomputes normalized prices
before atomic publication. Runtime parsing also verifies proof-bearing bundles;
missing/corrupt receipts make that market unavailable. Existing manually reviewed
bundle compatibility is retained. Prior and new bundles are retained by content
hash under `archive/{market}/`, so original inputs can be reproduced despite later
provider revisions. Do not remove referenced receipts when archiving bundles.

## Commands and update lifecycle

Run locally, using existing dependencies; no new service is installed:

```bash
.venv/bin/python -m src.paper.symbol_master refresh --market both
.venv/bin/python -m src.admin.collect_stress_evidence --market both
```

The collector is bounded to the reviewed catalog and does not execute on a web
request or add a scheduler job. Refresh explicitly when new evidence is wanted.
U.S. and Korea publish independently. A failed collection/import preserves the
previous installed market bundle; publication never serves a partial file.
The existing 20-observation summaries, 100-observation downside minimum,
non-overlapping sampling, same-date portfolio intersections and separate-market
outlook constraints are unchanged.

### Real end-to-end local verification

The project's original local current snapshots were stale (U.S. October 9,
Korea October 13), so the normal live analytics correctly withheld results.
An unchanged frozen-model refresh was run in **a separate operations directory**:

```bash
MARKET_OPERATIONS_DIR=/tmp/stress-evidence-demo/operations .venv/bin/python -m src.operations refresh --market both
.venv/bin/python -m src.admin.verify_stress_evidence --operations-dir /tmp/stress-evidence-demo/operations
```

The verifier refuses the default operations directory and production/staging mode.
It creates a brand-new disposable SQLite database under `/tmp`, provisions two
new research users, authenticates, requests real validated quotes, reviews
settlement, submits simulated orders, and calls `/api/paper/stress-analytics`.
Passwords/session secrets are randomly generated and never printed. No existing
user/account/session is selected or reset. The Korean order uses the unchanged
explicit USD→KRW settlement and fee logic. Full reports and a sanitized summary
are retained under ignored `data/paper/stress-evidence/examples/`.

The isolated refresh produced current provider-validated U.S. October 13 and Korea
October 14 snapshots. Their scores are outputs of the unchanged frozen models,
not new models or updates to the project's existing current snapshots or AWS.
See `real-stress-evidence-results.md` for the actual numerical run.

## Browser and remaining limits

The initial ingestion task changed no frontend files. Subsequent Chromium browser
QA on October 15, 2026 visually inspected the real NVDA/SK hynix paths, uncovered
Samsung, FX/cost confirmation, mixed-market holdings and desktop/responsive
English/Korean views, with safe frontend presentation fixes. Screenshots and
accounts are private local artifacts and are excluded from Git. See the
[current overview](../README.md) and [verification scope](real-stress-evidence-results.md).
Browser evaluation uses isolated operations state and disposable accounts; the
original freshness guard remains intact. After the U.S. publication boundary,
credit-input lag correctly withheld conditional U.S. results. No date, freshness,
model or sample-size override was applied.

Remaining unavailable cases include classifications/histories outside the six
reviewed instruments, unverified industries, unsupported venues, delisted or
changed identities, and insufficient or non-overlapping joint samples. Industry
benchmarks are descriptive evidence, not implicit stock substitutes. Security
history is preferred; only an explicit same-market sector mapping can be a
fallback. No market-index substitution, peer-name inference, historic membership
claim, causal assertion or recommendation is introduced.

The existing mixed-market combined-outlook limitation and fixed-current-FX
scenario assumption remain. Sector ETFs can change constituent/index methods;
these are actual fund histories under their historical mandates, not reconstructed
constant-composition sector indices. Full point-in-time taxonomy and universally
complete dividend/corporate-action verification require a stronger licensed data
source. Public deployment rights remain unconfirmed.

## Initial ingestion validation and change inventory (historical record)

- Full backend: **373 passed**, 2 existing warnings, 121.08 seconds.
- Focused ingestion/analytics run before the final two safety tests: 52 passed.
  The final full run includes all 22 new ingestion/safety cases.
- Frontend: all 50 tests and 1,085 bilingual message checks passed.
- TypeScript and production webpack build passed. No frontend source files changed.
- `git diff --check` passed.
- All 23 protected hashes, including six frozen models, operations/explainability,
  auth, password reset and completed-close provider, remain unchanged.
- The pre-existing build-info file matches its preservation baseline.
- Both real examples passed the authenticated API chain with strict freshness,
  corporate-action validation and original statistical minima. No browser
  screenshot or visual sign-off is claimed.

Files added in this task:

```
src/paper/stress_coverage.json
src/paper/evidence_pipeline.py
src/admin/collect_stress_evidence.py
src/admin/verify_stress_evidence.py
tests/test_evidence_pipeline.py
docs/real-stress-evidence.md
docs/real-stress-evidence-results.md
```

Existing uncommitted files extended in this task:

```
src/admin/import_stress_evidence.py
src/paper/stress_analytics.py
```

Local generated data: the existing Symbol Master database and private evidence
bundles/receipts/archives/examples under ignored `data/paper/`. Frozen-model refresh
artifacts and disposable trading databases live under `/tmp`; the project's
original current snapshots and accounts were not replaced. No AWS changes,
commit, push, deployment, account reset, scheduler change or new paid service.
