> Current preferred FX is [the delayed exchangerate.dev Free adapter](delayed-fx-provider.md); the optional licensed adapter described below remains disabled unless separately configured. Browser QA subsequently passed, and the order-result React warning was corrected. Validation counts and no-browser statements below describe the original execution-FX stage. See the [current overview](../README.md).

# Execution FX, portfolio exposure and reconciled outcomes

Market Stress Early Warning remains the primary product. Currency analytics are an evidence layer inside its portfolio workspace: they explain observed exposure and outcomes alongside market-stress status. They do not forecast securities, recommend trades, or claim market-stress/SHAP causality. The existing global navigation, market-stress hierarchy, models, MSI, SHAP, warning semantics, stock-price validation and scheduler are unchanged.

## Execution evidence and current FX

Every new Korean BUY **and SELL** requires the validated FX reference bound to its reviewed quote, even when no currency conversion is needed. `paper_order_costs.detail_json` stores the complete execution FX snapshot, exact decimal rate, original observation precision/date or timestamp, retrieval time, provider, status, actual spread (0 when not converting), effective conversion rate (null when no conversion), source/debit and destination/credit amounts, fees and a derived `execution_attribution` record. These are inserted in the same transaction as the order, native cash/positions and any `paper_fx_ledger` entry. A conversion record is not fabricated for a trade funded by existing KRW cash.

History uses the saved execution metadata; it never substitutes current FX. UPDATE triggers protect `paper_order_costs`, `paper_fx_rates` and `paper_fx_metadata`. The previously approved explicit demo reset can still delete owned trading records, preserving its private backup and once-only markers; it is not an ordinary history edit. No historical rows are backfilled or rewritten by this change. If an old trade lacks sufficient FX/cost evidence, reconciliation is unavailable rather than invented.

Current validated FX is separate and revalues all KRW cash and Korean securities. FRED retains its original date-only observation precision, null observation timestamp and daily/delayed wording. No intraday time is invented. Timestamped primary observations have a separate `paper_fx_metadata` row linked to the immutable rate ID. The existing visible-page refresh/focus behavior picks up new IDs without changing past executions.

Korean preview exposes price, quantity, KRW gross value, reference FX/provider/observation/retrieval, required USD conversion, actual spread/effective rate/conversion expense, commissions/taxes/regulatory costs, USD-equivalent net total, actual USD conversion debit and both remaining cash balances before confirmation. If native KRW covers a BUY, actual USD cash debit is zero and no conversion is claimed; the USD-equivalent order value is still shown.

## Average acquisition and cash bases

All rates R are **KRW per USD**. Computations use Decimal with 50-digit precision for attribution; execution continues using the original integer cents/won accounting and documented minor-unit rounding. No execution cash, native cost basis or realized-P&L rule is replaced.

Each position maintains:

- quantity q;
- gross native acquisition basis B_K (fees excluded);
- gross historical USD acquisition basis B_U = sum(gross native buy value / execution R);
- unallocated historical purchase fees F_U = sum(buy fees / execution R).

Multiple purchases add to all bases. A sale of n shares allocates fraction n/q of each basis, leaving the rest for remaining shares. This is an average gross-cost method, not FIFO and not the latest purchase FX. Average acquisition FX is **B_K/B_U**, an effective harmonic rate weighted by acquisition notional. Average gross purchase price is B_K/q. Purchase fees are tracked separately for attribution, while the original execution engine still capitalizes them in native accounting. Small differences between proportional analytic allocation and integer native basis allocation are not relabeled FX; native execution P&L remains separately reported.

For an open Korean position, with current gross market value V_K and validated current rate R:

```
native stock P&L (KRW) = V_K - B_K
native investment effect (USD) = (V_K - B_K) / R
FX translation effect (USD) = B_K / R - B_U
open-position net USD P&L = native effect + FX effect - remaining purchase fees F_U
```

USD/KRW percentage change = (R / average acquisition FX - 1) × 100. A positive percentage means KRW weakened against USD, not that investment performance improved. Position-level conversion cost is not allocated arbitrarily: conversion expense remains a portfolio-level expense.

At a sale, let S_K be gross proceeds, R_s the frozen sale execution rate, b_K/b_U/f_U allocated purchase bases, and T_K sale fees:

```
native realized stock P&L = S_K - b_K
native sale effect USD = (S_K - b_K) / R_s
realized security FX effect USD = b_K / R_s - b_U
net realized sale result USD = native sale effect + security FX effect - f_U - T_K/R_s
```

The immutable sale record contains purchase FX basis b_K/b_U, sale FX, all components and the net result. Sale proceeds stay in KRW under the existing settlement policy.

KRW cash has its own average historical USD carrying basis C_U and native balance C_K. Currency converted into KRW adds KRW/reference R to C_U. Net KRW sale proceeds add net proceeds/R_s. Spending/consuming x KRW removes average basis C_U × x/C_K and recognizes cash FX effect **x/R_execution - removed USD basis**. KRW cash remaining at valuation contributes unrealized cash FX **C_K/R_current - C_U**. A subsequent FX move after selling therefore continues to affect cash, without counting a stock's earlier FX effect twice.

USD→KRW conversion expense = actual USD debit − actual KRW credit/reference R. KRW→USD expense = actual KRW debit/reference R − actual USD credit. This includes spread and integer rounding; it does not pretend to be pure spread alone. Both conversions use the exact original validated reference, while actual effective bid/ask-like rates remain separately recorded.

## Portfolio reconciliation

Aggregate gross realized investment effects at execution FX plus open investment effects at current FX. Add realized security/cash FX and current unrealized security/cash FX. Deduct **all** historical trading fees valued at their respective execution FX and all recorded conversion expenses exactly once:

```
net exact USD result = native investment effect
                    + FX translation effect (securities + cash)
                    - historical USD trading costs
                    - historical USD conversion costs
```

The native execution books already deducted costs from cash. This formula is an explanation of their value, not another cash deduction. USD holdings use the same gross-basis decomposition with R=1. Full cash and position histories must match the actual ledger. The exact result must match displayed total portfolio P&L to within half a cent. The explicitly reported rounding residual reconciles the unrounded explanation to the displayed cent total; any larger mismatch makes attribution unavailable. No unexplained residual is labeled FX.

KRW exposure USD = (KRW cash + Korean asset value)/current R. KRW exposure share = that amount/current total USD equity × 100. This is observed currency exposure; it is not a new model risk score or a stress scenario.

## Deterministic examples (zero fees/spread except the cost example)

Buy 10 shares at ₩50,000 using R=1,000: gross native basis ₩500,000 and historical USD basis $500.

| Current price | Current R | Native investment effect USD | FX effect USD | Total USD result |
|---|---:|---:|---:|---:|
| ₩60,000 | 2,000 | +50 | −250 | −200 |
| ₩40,000 | 500 | −200 | +500 | +300 |
| ₩60,000 | 500 | +200 | +500 | +700 |
| ₩40,000 | 2,000 | −50 | −250 | −300 |

Buy another 10 shares at ₩50,000 with R=2,000: total native basis ₩1,000,000; USD basis $750; average FX 1,333.333… (not 2,000). Sell 10 at ₩60,000 with R=2,000: allocate ₩500,000/$375; local USD effect +50, security FX −125, net sale result −75. Remaining 10 shares have the same average bases. Retain ₩600,000 proceeds: at R=1,000 the cash has +$300 FX gain since sale; total portfolio result is +$450 including the remaining position. The test also reuses retained KRW for a BUY without fabricating a conversion.

With default costs, first BUY at R=1,000 costs ₩75 commission, converts $500.58 into ₩500,079 at effective 999, and leaves ₩4 cash. Historical trading expense is $0.075; conversion expense is $0.501; exact result −$0.576 rounds to −$0.58 with a −$0.004 displayed rounding residual. Partial sales, later FX changes and reverse conversions are also tested for reconciliation.

## Higher-frequency research and architecture

Research checked official provider material; marketing use of “real-time” is not treated as a contractual latency guarantee. No provider subscription was purchased, no new feed enabled, and no live-key/provider calls were made during tests.

| Option | USD/KRW / history | Frequency / reliability | Limits, price, public-display rights |
|---|---|---|---|
| Twelve Data | [Explicit USD/KRW instrument](https://twelvedata.com/markets/938314/forex/usd-krw); [forex/history](https://twelvedata.com/forex) advertises intraday and historical access; pair-specific retention depends on plan. | Timestamped exchange-rate REST endpoint; no app-specific guaranteed latency contract established. SLA depends on plan; no uptime guarantee inferred for free tier. | [Individual Basic](https://twelvedata.com/pricing): 8 credits/minute, 800/day, internal non-display restrictions; **not** a production public-display license. [Business plans](https://twelvedata.com/news/march-2026-updates) list Venture $499/month and Enterprise $1,099/month. [Terms](https://twelvedata.com/terms) require explicit display/redistribution rights; [attribution](https://support.twelvedata.com/en/articles/12647398-attribution-guidelines-for-using-twelve-data) requires a visible dofollow provider link unless contract says otherwise. |
| ExchangeRate-API | [KRW/history](https://www.exchangerate-api.com/docs/historical-data-requests), historical data on paid plans, daily reference history. | [Open/free](https://www.exchangerate-api.com/docs/free) daily; [Pro](https://www.exchangerate-api.com/) hourly, Business every 5 minutes. Redundant infrastructure advertised; no SLA independently established. | Open requires attribution, permits commercial conversion but not raw redistribution; free keyed plan 1,500 requests/month, daily updates. Pro $10/month/30k requests; Business $30/month/125k. A daily free plan does not solve the requested intraday requirement. |
| FRED DEXKOUS | [Daily USD/KRW observations](https://fred.stlouisfed.org/series/DEXKOUS), historical date-only observations. | Delayed H.10 publication, existing validated fallback/reference; no real-time guarantee. | Existing key retained; no new paid service. Original freshness limits remain unchanged. |

The optional primary adapter is Twelve Data, **disabled by default**. Operator prerequisites: `PAPER_FX_PRIMARY_PROVIDER=twelve_data`, `TWELVE_DATA_API_KEY`, and `PAPER_FX_PRIMARY_LICENSE_CONFIRMED=true` only after obtaining adequate external-display rights. The adapter validates exact symbol, positive finite decimal rate, provider identity and UTC timestamp. API errors never expose credential-bearing URLs.

Primary observation and retrieval ages must each be at most 300 seconds; future timestamps fail. Cache refresh is demand-driven at 120 seconds (serialized per API worker, with failure retry backoff), nominally at most 720 successful periodic fetches/day per worker; retries and additional workers require quota review. This is not a claimed provider update SLA. Each primary snapshot stores an immutable timestamp row. If primary is unavailable, stale, misconfigured or unlicensed, FRED is independently validated and explicitly labeled **daily fallback**. If neither source is valid, FX-dependent execution is blocked. Cached primary data is not served when display-license confirmation is absent.

Compose passes these optional variables with the primary disabled. Stock execution remains validated completed **daily close** regardless of FX frequency. Enabling higher-frequency FX does not make stock execution real-time. Provider rights/plan verification is the remaining prerequisite; an environment confirmation is an operator assertion, not a license procurement mechanism.

## Files changed for this requirement

Earlier uncommitted work remains in place. This requirement changes:

```
src/paper/fx.py                         validated primary/cache/fallback selection and exact FX metadata
src/paper/fx_primary.py                 new disabled-by-default timestamped provider adapter
src/paper/fx_performance.py             new execution replay and reconciled currency attribution
src/paper/investment.py                 all-Korean-trade FX validation, explicit USD preview, exposure response
src/paper/service.py                    immutable execution explanation and exact minor-unit valuation field
src/paper/router.py                     owned transaction history includes saved execution details
src/paper/store.py                      timestamp metadata table and immutable-update guards
frontend/src/app/paper-trading/types.ts
frontend/src/app/paper-trading/PortfolioWorkspace.tsx
frontend/src/app/paper-trading/TradeTicket.tsx
frontend/src/app/paper-trading/paper-trading.css
frontend/src/app/i18n/en.json
frontend/src/app/i18n/ko.json
frontend/tests/i18n.test.cjs             bilingual rendering of reconciliation and execution history
tests/test_execution_fx.py              deterministic economic/provider/history regression tests
deploy/docker-compose.staging.yml       optional primary FX environment, disabled defaults
deploy/staging.env.example              optional configuration placeholders only
docs/execution-fx-attribution.md
docs/single-capital-portfolio.md         link superseding FX attribution notes
docs/realistic-paper-trading-costs.md    link superseding FX attribution notes
```

No Market Risk page, model file, SHAP implementation, MSI, scheduler, Security Master, price-provider validation, authentication, account role, password-reset command or demo reset implementation was changed for this requirement. No real database migration/reset was executed. The provider adapter is packaged by the existing `COPY src/paper` Docker instruction; no parallel service or dependency was added.

## Final validation

- Full backend: **282 passed**, 2 existing warnings, 113.05 seconds.
- New deterministic execution-FX cases: **14 passed**. Focused FX/cost/demo-migration regression group: **44 passed**.
- Frontend: **40 workflow tests passed**, plus **1,041 bilingual message checks** and new bilingual rendering assertions for FX reconciliation, unavailable evidence, and historical execution rates.
- TypeScript and production webpack build passed.
- `git diff --check` passed.
- All 23 protected-file hashes, including the six frozen model files, operations/scheduler, explainability, authentication, password reset and stock-price provider, remained unchanged. The pre-existing build-info file change was preserved.
- Existing Starlette/httpx and XGBoost smoke-test warnings and unrelated React list-key warnings remain.
- No browser screenshot captured; no visual-browser sign-off claimed. No live provider call, license purchase, AWS action, account reset, commit or push.
