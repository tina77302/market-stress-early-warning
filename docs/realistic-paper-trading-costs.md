> Current FX selection is [exchangerate.dev Free preferred with FRED fallback](delayed-fx-provider.md), and reconciled execution FX follows [this contract](execution-fx-attribution.md). Browser QA subsequently passed with disposable accounts; tests/counts and unavailable-browser statements below are historical records of the original cost implementation. See the [current project overview](../README.md).

> FX execution evidence, the optional timestamped primary provider, and reconciled attribution now follow [execution FX and portfolio outcomes](execution-fx-attribution.md). This supersedes the earlier unavailable-attribution limitation.

# Cross-market Paper Trading: execution and cost policy

This completes the existing uncommitted unified workspace. The final authorized demo reset is implemented separately in the [demo migration procedure](demo-account-migration.md); it has been tested on temporary databases and has not been applied to AWS. Authentication, security discovery, validated completed-close prices, risk models, attribution and scheduler are preserved. This is simulated trading, not a real broker or personal tax calculation.

## Capital, FX and accounting

New accounts have one USD 100,000 contribution and KRW 0, represented by two native-currency subledgers. All three account provisioning paths use the same initializer. Existing accounts without the unified capital record fail closed for new unified trading; their original records remain intact. See [migration plan and read-only AWS audit](single-capital-portfolio.md). AWS admin1/user1 balances have not been inspected from this environment. Run the explicit demo-account migration during the approved deployment maintenance window; startup never silently resets trading data.

FX uses [FRED DEXKOUS](https://fred.stlouisfed.org/series/DEXKOUS), Federal Reserve H.10 daily observations, through the existing `FRED_API_KEY`. This is the latest available dated observation, with publication lag, not an intraday or real-time feed. The provider supplies an observation date, not an intraday timestamp; the public timestamp is explicitly null with date precision. Each immutable reference stores its original observation date, UTC retrieval time, decimal rate and source. Available/stale status is computed from freshness validation, never obtained by relabeling the original date. Maximum observation age is 10 calendar days and retrieval age 6 hours; fetch cache is 1 hour. A provider failure can reuse a valid cached rate within these limits. Missing, future, stale, nonpositive or nonfinite rates cannot fund conversion. Stock quote validity remains separately enforced.

The visible workspace checks FX every 60 seconds and on focus and revalues when a new reference arrives. This refresh does not claim real-time prices. Historical orders and their FX records are never recalculated. Valuations carry the newly used reference; new valuation history contains only actual recorded observations, never synthetic points.

Native cash pays first. A BUY shortfall is funded from the other currency only after reviewing the complete preview. The configurable default spread is **10 bps (0.10%) each conversion**: USD to KRW uses reference × 0.999, KRW to USD uses reference × 1.001. Source debit rounds up to its smallest unit; destination credit rounds down. Any residual stays in cash. Exact historical USD conversion cost measures the difference between reference-valued source and destination, including integer rounding. It is stored with the reference, actual applied rate and spread. This measures recorded conversion expense, not a complete portfolio FX-return attribution.

BUY deducts gross plus fees and capitalizes these fees into position cost basis. SELL credits net proceeds and realizes net proceeds minus allocated cost basis. Unified value translates native holdings and cash at the currently validated FX; fees/spread are already reflected in cash and are **not deducted twice**. Realized/unrealized trading P&L and cumulative native fees translated to current USD are labeled as translations, not historical realized FX attribution. No separate FX-gain figure is fabricated.

Preview tokens bind owner, quote, side, quantity, full dated cost policy, FX and both post-trade balances. Execution recomputes the plan under `BEGIN IMMEDIATE`; changed balances or any mismatched plan require review again. Orders, positions, both cash balances, cost records and conversion events commit together or roll back together. Idempotent accepted retries return the original execution, including after quote expiry, without charging again. No password/session/CSRF or role policy changes are involved.

## Configured simulation assumptions

`src/paper/cost_rules.json` is the single versioned policy. Optional `PAPER_COST_CONFIG_PATH` selects another validated JSON file inside the API container. Default version `sim-costs-2026-10-15-v1` covers 2026-01-01 through 2026-12-31. Beyond that period trading fails closed until the schedule is reviewed. Runtime validation uses explicit exceptions, including under Python optimization. Each quote freezes canonical policy JSON and SHA-256 plus security type, exchange and local execution date (New York/Seoul). Crossing a date boundary requires a new quote. Each executed order preserves its full breakdown independently of quote retention or later policy changes.

| Component | Default |
|---|---|
| US Stock / ETF BUY and SELL commission | 0; configurable independently by type and side |
| Korea Stock / ETF BUY and SELL commission | 1.5 bps = 0.015%; independently configurable |
| Minimum commission | 0 native minor units; configurable by market |
| Korea KOSPI Stock SELL | 0.05% securities transaction tax + 0.15% agricultural special tax |
| Korea KOSDAQ Stock SELL | 0.20% securities transaction tax |
| Korea ETF transaction tax | Exempt; no stock transaction tax applied |
| US SELL SEC Section 31 pass-through assumption | 0 before April 4, 2026; $20.60 per million from April 4 |
| US SELL FINRA TAF pass-through assumption | $0.000195/share, cap $9.79 through September 30; 0 during October–December 2026 holiday |
| FX conversion | 10 bps adverse spread plus minor-unit rounding |

US commission and regulatory fees round up to cents; Korean commission and each separate tax component round down to won. TAF is capped before rounding. Exact simulated broker rounding can differ from a real broker's aggregate remittance process. Effective dates use the simulated trade date; this daily-close simulator does not implement an actual broker settlement/charge-date calendar. The preview states that assumptions are simulated and shows zero components too. Unknown tax classification, invalid configuration or uncovered regulatory dates fail closed.

Commission defaults are broker-like examples, not universal prices or an exact broker replica: [Fidelity commission schedule](https://www.fidelity.com/trading/commissions-margin-rates/) and [Kiwoom online commission example](https://download.kiwoom.com/hero4_help_new/0220.htm). Promotions, routing, account eligibility and product-specific exceptions can differ.

Regulatory/tax sources reviewed for the 2026 policy:

- [SEC 2026 fee advisory 2](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2): $20.60/million effective April 4. [SEC explanation](https://www.sec.gov/answers/sec31.htm): this is assessed on SROs; customer pass-through is a simulation assumption, not a universal direct investor tax.
- [FINRA 2026-021 holiday filing](https://www.finra.org/rules-guidance/rule-filings/sr-finra-2026-021), [SEC filing](https://www.sec.gov/files/rules/sro/finra/2026/34-106409.pdf) and [2026 rate schedule filing](https://www.finra.org/sites/default/files/2024-11/sr-finra-2024-019.pdf).
- [Korean securities transaction tax decree](https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=280901), [2026 amendment details](https://www.law.go.kr/lsInfoP.do?chrClsCd=010102&lsiSeq=282431&viewCls=lsRvsDocInfoR) and [Korea Investment securities trading disclosure](https://file.koreainvestment.com/updata/namo/30182804%EC%A3%BC%EC%8B%9D%EA%B1%B0%EB%9E%98%EC%84%A4%EB%AA%85%EC%84%9C_%EC%8B%A0%EA%B5%AC.pdf).
- [KRX ETF taxation guidance](https://regulation.krx.co.kr/contents/RGL/03/03060105/RGL03060105.jsp): ETF transaction-tax exemption; older generic stock rates on guidance pages are not used for current stock taxes.

Personal capital-gains tax, dividends, fund-specific ETF income withholding, investor residency/exemptions, ADR charges and venue-specific liquidity fees/rebates are **not modeled**. In particular, ETF transaction-tax exemption does not imply exemption from all ETF income taxes. No reliable investor tax/NAV basis exists here to invent withholding. Korean venue/clearing costs are not separately added to the broker-like commission; no duplicate exchange charge is guessed.

## Licensed data assessment; daily-close execution retained

| Provider | Data / latency | Published cost / licensing assessment |
|---|---|---|
| [Alpaca](https://docs.alpaca.markets/us/docs/about-market-data-api) | US Basic real-time IEX only; full SIP access delayed 15 minutes. AlgoTrader Plus offers real-time SIP. | Plus $99/month personal tier; business tiers and redistribution agreements differ. A personal subscription does not establish this multiuser app's redistribution rights. |
| [KRX/Koscom](https://data.krx.co.kr/inc/datasale/Market%20Data%20Product%20Brochure.pdf?v=20250732) | Official real-time Korea feeds over contracted network/Internet services; no guaranteed latency inferred. | Contract-specific fees; external redistribution requires relevant Koscom agreements. No verified fixed public quote or license for this app. |
| [Korea Investment Open API](https://apiportal.koreainvestment.com/) | Brokerage-account/token-based real-time WebSocket services. | Suitability and redistribution pricing/rights for a multiuser simulator are unverified; not assumed free for public redistribution. |
| [OANDA FX data](https://www.oanda.com/foreign-exchange-data-services/en/exchange-rates-api/) | Commercial REST/FIX/streaming FX; real-time offering available, no latency SLA assumed. | Advertised FX plans from $4,850/year; real-time/custom redistribution terms require a quote/agreement. No new subscription purchased. |
| [FRED](https://fred.stlouisfed.org/docs/api/fred/series_observations.html) | Dated daily H.10 observations with publication lag. | Uses the existing API key; not real-time. Provider terms still apply. |

No suitable licensed intraday integration has been established for this deployment. Existing validated completed daily close price execution remains intact. This assessment does not assert that the existing Yahoo source automatically grants public redistribution rights; production licensing remains an operational prerequisite. No paid API or brokerage execution integration was added.

## Review and operational limits

The full local uncommitted file inventory is captured in the completion report. New deterministic cost tests use the production policy, while legacy zero-cost arithmetic tests opt into a temporary zero-cost test policy explicitly. Tests use mocked market data, never real trading or real account migration. Browser screenshot validation is unavailable in this environment, so no visual sign-off is claimed. Fee schedules require review after 2026 or whenever the relevant authority changes a rule. AWS deployment, licensed-feed procurement and applying the implemented demo reset remain separate operational steps.

## Completion validation and exact file inventory

Final validation:

- `.venv/bin/python -m pytest -q`: **263 passed**, 2 warnings, 96.33 seconds. Warnings: Starlette/httpx deprecation and an existing XGBoost smoke-test unused parameter.
- `.venv/bin/python -m pytest tests/test_realistic_costs.py -q`: **25 passed**, 1 Starlette/httpx warning. Re-run after strengthening historical execution immutability with a new FX valuation reference.
- `npm test --prefix frontend`: **40 workflow tests passed**, plus **1,012 bilingual message checks**. Existing React list-key warnings in unrelated validation components remain.
- `npm run typecheck --prefix frontend`: passed.
- `npm run build --prefix frontend -- --webpack`: passed; all 13 pages generated.
- `git diff --check`: passed.
- SHA-256 comparison of 23 protected files (including all 6 frozen model files, operations/scheduler, explainability, authentication, password reset and completed-close provider): unchanged.
- Existing locally modified `frontend/tsconfig.tsbuildinfo` matches the pre-task preservation baseline; it was not reset or included in this work.
- No browser screenshot captured. No live AWS/provider tests or real-account migration performed. No commit, push or deployment.

This continuation changed only:

```
src/paper/costs.py
src/paper/investment.py
tests/test_realistic_costs.py
frontend/tests/paper-workflow.test.cjs
docs/realistic-paper-trading-costs.md
docs/single-capital-portfolio.md
docs/unified-paper-trading.md
```

These earlier uncommitted implementation files were preserved and validated, without reimplementing completed work:

```
frontend/package.json
frontend/src/app/api/workspace/[...path]/route.ts
frontend/src/app/i18n/en.json
frontend/src/app/i18n/ko.json
frontend/src/app/paper-trading/MarketRiskPanel.tsx
frontend/src/app/paper-trading/PortfolioWorkspace.tsx
frontend/src/app/paper-trading/SecurityPicker.tsx
frontend/src/app/paper-trading/TradeTicket.tsx
frontend/src/app/paper-trading/page.tsx
frontend/src/app/paper-trading/paper-trading.css
frontend/src/app/paper-trading/types.ts
frontend/src/app/paper-trading/workflow.ts
frontend/tests/i18n.test.cjs
src/admin/audit_portfolios.py
src/paper/accounts.py
src/paper/admin.py
src/paper/router.py
src/paper/service.py
src/paper/store.py
src/paper/fx.py
src/paper/cost_rules.json
tests/conftest.py
tests/test_multi_admin.py
tests/test_paper_workspace.py
tests/test_security_discovery.py
tests/test_username_accounts.py
tests/test_unified_investment.py
```

Unrelated `README.md.backup`, `src/experiments/*` and the pre-existing build-info change were left alone. Nothing was staged.
