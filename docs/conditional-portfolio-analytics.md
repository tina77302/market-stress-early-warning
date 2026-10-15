# Conditional market-stress and portfolio evidence, version 1

Market Stress → Sector/Industry Stress → My Exposure → Historical Sensitivity →
10D Outlook is the standard registered-user experience. Roles and plans never
select analytics quality. This layer does not run, train, recalibrate or modify
any model. Historical association is not causation or a guaranteed forecast.

## Inputs and market separation

Read the existing validated current snapshot through
`src.operations.service.current_payload`. Analysis requires `data_health.is_current`
and an available model. Preserve snapshot date, ID and model checksum. Read the
existing U.S. `processed/oos_predictions.csv` and Korea
`processed/korea/korea_oos_predictions_10d.csv` XGBoost OOS outputs independently.
These are walk-forward model outputs, **not historical outputs of today's frozen
model**. No historical predictions are regenerated. Model drift across folds and
between the OOS models and today's frozen model is a limitation.

Comparable environments use the application's existing displayed regimes:
U.S. LOW <30, WATCH [30,50), ELEVATED [50,70), HIGH >=70 on the displayed one-decimal
risk score. Korea uses its existing WARNING vs BELOW WARNING reference at 0.50
on the original historical XGBoost output, and the current snapshot's explicit
`warning_active` boolean when present. These are existing product categories,
not newly estimated sector thresholds. MSI, scores, warning semantics, model
files and refresh operations are unchanged. No U.S. bands are applied to Korea.

Session calendars use the existing exchange-calendars dependency with the same
XNYS/XKRX identities as the refresh calendar. Market-context price histories come from the existing
`raw/raw_market_data.csv` SPY series and `raw/korea/krx_indices.csv` KOSPI200 series.
Non-session raw rows are excluded using the exchange calendar; missing marks on
actual exchange sessions remain missing and invalidate the affected outcomes.
Market-context returns are explicitly labelled price-series context, not
adjusted sector evidence or a portfolio forecast. The layer never reads targets
or forward returns to select environments.

## Sampling and statistics

Within each market, iterate historical OOS dates chronologically. Select the
first date in the current regime whose full ten subsequent market sessions end
on or before the current validated snapshot date. After selecting a date, exclude
additional starting dates in its next ten-session outcome interval. The next
eligible observation can start at the preceding outcome's ending close; return
intervals have disjoint daily increments. This avoids inflating sample counts
with overlapping ten-day outcomes. Event dates are chosen before instrument
returns are inspected. An instrument needs all 11 positive finite closes on the
market calendar; missing sessions are never compressed, filled or interpolated.

Use arithmetic holding-period returns, `(adjusted_close[t+10]/adjusted_close[t]-1)`.
Publish n and event dates/outcomes. At n>=20 publish median, Q25/Q75, negative-return
frequency, IQR and sample standard deviation. At n>=100 publish downside Q10.
Quantiles use NumPy's deterministic linear empirical interpolation. At n<20
withhold summary estimates and charts, preserving the sample count. These
conservative reporting cutoffs are not market risk thresholds or a significance
test. Serial dependence, persistence and small tail samples remain possible;
no independent-sample claim, confidence interval or calibrated probability is
made. Sample counts are instrument-specific and joint portfolio counts may be
smaller. Zero-return observations are not negative returns.

## Verified instrument evidence

The existing listing master has no sector/industry classifications and the
repository has no adjusted sector/security historical universe. Do not infer
classifications from tickers, company names, market indices or SHAP drivers.
An unavailable sector history is not an inferred sector risk score.

An operator can supply a reviewed, provenance-tagged JSON bundle to the **local**
importer; no provider research, API subscription or automatic network ingestion
is introduced. Nothing is imported or activated by startup. The importer checks
canonical symbols, currencies and active listings against the existing local
security master in read-only mode, validates the complete evidence bundle, then
atomically replaces only `data/paper/stress-evidence/{market}.json`. Rejected
imports preserve the previous file. These files are analytics inputs, never
execution FX or trading records. No portfolio/database migration is required.

Bundle schema (structural illustration only; do not publish these placeholders):

```json
{
  "schema_version": 1,
  "market": "us",
  "instruments": [{
    "symbol": "CANONICAL_LISTING_SYMBOL",
    "currency": "USD",
    "kind": "security",
    "source": "https://provider-or-issuer.example/verified-evidence",
    "reviewed_at": "ISO-8601 timezone-aware review timestamp",
    "sector": "Provider-reported sector, or omit if unknown",
    "industry": "Provider-reported industry, or omit if unknown",
    "return_basis": "split_and_dividend_adjusted_close",
    "prices": [{"Date": "YYYY-MM-DD", "Close": "positive adjusted price"}]
  }]
}
```

`kind` may be `security`, `sector`, or `industry`. Sector/industry instruments
must be listed ETFs and carry the corresponding reviewed classification;
non-listed indices and synthetic baskets are not accepted in this version. A security may declare
`sector_proxy` pointing to a sector instrument in the same bundle with exactly
the same reviewed sector. No proxy is selected by favorable historical results.
The importer sets `identity_verified`; it never guesses classification. Empty
price arrays permit classification-only security metadata, but produce no return
evidence. Classification and adjusted-price provenance must be reviewed by the
operator; the software cannot independently certify a supplied source's accuracy
or usage rights. Retain a combined evidence source document where necessary.
Historical classification changes, universe selection and survivorship bias
remain limitations. This is current-exposure analysis, not an investable backtest.

Explicit command, only after reviewed real evidence is available:

```bash
.venv/bin/python -m src.admin.import_stress_evidence --market us --file /path/to/reviewed-us.json
```

Repeat independently with `--market korea`. The subsequent [reviewed real-data pipeline](real-stress-evidence.md) installed six instruments locally through this importer; those private bundles are not included in Git or deployment artifacts.
The API response includes SHA-256 hashes for OOS, calendar and evidence inputs.
Store input artifacts alongside the response for exact later reproduction.

## Exposure, sensitivity and outlook

The authenticated `/api/paper/stress-analytics` endpoint uses the existing
owner-scoped unified investment summary and its validated prices/current FX.
No user selector, role gate or plan gate is accepted. USD-equity denominators
include cash. Market/sector/industry/security groups describe invested holdings;
currency includes cash. Unknown classifications remain explicit. Missing
valuation or required FX makes weights unavailable. Preserve each holding's
market, currency, sector, industry, metadata provenance and weight.

Prefer security adjusted-history evidence when n>=20. Otherwise use only an
explicitly reviewed same-market sector mapping with n>=20; expose that evidence
level and instrument. Never substitute the market benchmark for missing sector
or security data. Industry evidence is displayed when supplied but is not an
implicit security proxy in this first version.

For a market's portfolio contribution, intersect event start **and end** dates
across every held instrument. Apply actual current USD-equity weights to each
joint historical outcome, then compute the aggregate empirical distribution.
Never sum marginal quantiles or assume holdings are independent. Any uncovered
holding blocks the aggregate. A sufficiently small joint sample withholds
summary estimates even if every instrument individually has a larger sample.

These are buy-and-hold conditional scenarios: current validated FX is held
constant, cash return is zero, no future trades or additional execution costs
are assumed. Adjusted history includes instrument distributions. No future FX
scenario or recommendation is generated. Historical FX records, portfolio
accounting and fee/execution rules remain unchanged. A market contribution is
measured against total equity, not normalized to just that market's holdings.

A whole-portfolio 10D distribution is shown only when the portfolio has invested
holdings in one market and complete joint evidence. Cash-only accounts receive
no stock outlook. For portfolios invested in both markets, display independent
market contributions and withhold a combined range until joint cross-market
sampling with aligned horizons is supported. Do not pair independent stress
events, assume correlation, add quantiles or apply one market's regime to another.

Actual Performance remains a separate recorded-history chart. The five-stage
analytics panel shows descriptive histograms/cards and provenance. Results are
conditional historical scenarios, with one-decimal presentation to avoid false
precision. Missing inputs are explicitly unavailable rather than numerical
placeholders. No AI-generated recommendation, plan restriction or new service
is involved.
