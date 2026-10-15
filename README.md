# Financial Market Stress Early Warning & Portfolio Risk Analytics

A non-commercial research and portfolio/demo application for monitoring broad financial-market stress in the **U.S. and Korea**, then examining how a user's actual simulated portfolio is exposed to historically similar environments.

**Market Stress Early Warning is the core product.** Paper Trading, FX and portfolio analytics connect market conditions to portfolio exposure and recorded outcomes. The system does not predict individual stock prices, provide stock recommendations, or promise future returns.

```text
Independent U.S. / Korea Market Stress
    → Sector / Industry Stress
    → My Portfolio Exposure
    → Historical Stress Sensitivity
    → Historical conditional 10D Outlook
```

## Independent market-stress systems

| | U.S. | Korea |
|---|---|---|
| Equity input | SPY | KOSPI200 |
| Volatility input | VIX | VKOSPI |
| Credit input | Moody's Baa yield minus U.S. 10-year Treasury yield | Korean corporate AA− 3-year yield minus Treasury 3-year yield |
| Primary warning horizon | Next 10 trading days | Next 10 trading days |
| Model specification | Existing 17-feature specification | Separate existing 17-feature specification |
| Models | Logistic Regression baseline and XGBoost | Separate Logistic Regression baseline and XGBoost |
| Current inference | Frozen U.S. XGBoost model | Frozen Korea XGBoost model |
| Regime presentation | Existing LOW / WATCH / ELEVATED / HIGH bands | Existing Korea WARNING / BELOW WARNING reference |

Each market retains its own MSI construction, historical distribution, stress-event definition, targets, model artifacts and warning semantics. **U.S. thresholds, bands and regimes are never applied to Korea, or vice versa.** The dashboard's U.S./Korea comparison places the independent systems alongside each other; it does not pool or normalize their models into a common probability scale.

The **Market Stress Index (MSI)** describes observed market conditions. The **10-trading-day Risk Score** is a model-based forward warning signal, not a calibrated probability. A score of 70 does not mean a 70% event probability, and equal scores across markets need not imply equal event likelihoods.

### Validation and explanation

Historical model evaluation uses **chronological, expanding walk-forward out-of-sample validation**, with a label-overlap purge appropriate to the forward horizon. Random train/test splitting is not the validation design. Incomplete forward targets remain unknown instead of becoming artificial negative labels. U.S. multi-horizon diagnostics additionally cover 1, 5, 10 and 20 trading days; they are distinct tasks with different target prevalence.

Logistic Regression provides the linear reference and XGBoost the nonlinear comparison/deployment model. The validation pages report their trade-offs using the existing OOS artifacts; neither is described as a universal winner. See the market-specific validation pages and [methodology source](src/korea/korea_walk_forward.py) rather than treating a static README metric as a current production result.

**SHAP explains contributions to the fitted model's output.** It does not establish causality or probability-point changes. Current channel summaries show net contributions among available leading drivers and their strongest representative feature. Detailed SHAP remains the evidence layer below them.

During a successful refresh, attribution uses the exact validated feature row and the same frozen model/checksum as the result. Observation dates, feature provenance and model identity must agree. Snapshot-bound attribution is published with the validated snapshot; stale or mismatched attribution is rejected rather than relabelled. See [snapshot attribution](docs/snapshot-attribution.md).

## Automated refresh and freshness safeguards

The API's optional embedded scheduler runs independent U.S. and Korea refresh jobs using exchange calendars, publication deadlines, per-series expectations, bounded provider calls and per-market locks. `MARKET_REFRESH_ENABLED` controls it; the staging template deliberately defaults to disabled until the controlled first refresh is approved. A running deployment's actual setting and heartbeat must be checked separately.

Refresh retrieves market inputs, validates provenance/dates/values, computes the existing features and MSI, and performs inference with the **frozen models**. It does not retrain, recalibrate or change model thresholds. Staged artifacts and a transactional snapshot pointer protect readers from partial publication. Failures preserve the last-known-good snapshot; the API separately exposes the latest attempt, observation/publication timestamps, model availability and freshness status.

A last-known-good score may remain visible with a clear delayed/stale warning. **Conditional sector/portfolio analytics intentionally become unavailable when required current market inputs fail freshness checks**, even if prices or an older model score remain available. Successful provider retrieval alone does not make an old observation current. One market's failure does not make the other market unavailable.

For example, during local evaluation on October 15, 2026, the U.S. publication boundary advanced while FRED credit observations still ended October 13. The existing refresh succeeded using the validated common row, but U.S. health became `DELAYED` and conditional analytics were withheld. No dates or safety limits were overridden to keep charts populated.

See [reliability rules](docs/data-reliability.md) and [automation review](docs/data-automation-review.md).

## Unified Paper Trading

Every newly registered user receives **one conceptual portfolio**:

- Base currency: **USD**; initial total capital: **$100,000**.
- Initial cash: **USD $100,000 and KRW ₩0**.
- Initial positions, orders, realized/unrealized P&L and accumulated costs: zero.
- One total equity, USD P&L and recorded performance history across both markets.

The two database `portfolios` rows are internal native-currency settlement ledgers, **not independently funded USD/KRW portfolios**. Market filters change presentation, not ownership, capital or settlement rules.

The unified security picker searches existing U.S. and Korea Symbol Master identities by ticker/company name, including Korean names and symbols. Selecting a listing automatically selects its market/currency and fetches a validated **completed daily-close** quote. Security-discovery coverage is broader than the small reviewed analytics-evidence universe; a searchable security is not automatically covered by historical analytics.

The order ticket supports simulated whole-share BUY/SELL, quantity-driven estimates, ownership/expiry checks, available-share and cash limits, and explicit final review. Native cash pays first. Any required cross-currency shortfall conversion must be reviewed and accounted for; Korean purchases cannot create free KRW. Margin, leverage, short selling, fractional shares and real brokerage execution are not provided.

Server-approved previews bind the quote, quantity, dated cost policy, FX and cash state. Orders, positions, cash, cost details and conversion events commit together or roll back together. Accepted idempotent retries return the original execution rather than charging again.

**Admins and normal users have identical trading and analytics functionality.** Admin roles provide administrative privileges only. There are no Free/Pro tiers, paywalls, upgrade prompts or plan-based analytics gates. A future AI Risk Advisor is not an implemented recommendation service. See [access policy](docs/product-access-policy.md).

### Delayed FX and costs

| FX source | Role | Application acceptance/cache policy |
|---|---|---|
| exchangerate.dev Free | Preferred latest-available USD/KRW source, approximately **15-minute delayed** | Independent observation age ≤30 minutes; retrieval age ≤15 minutes; on-demand shared refresh after 10 minutes |
| FRED DEXKOUS / Federal Reserve H.10 | Delayed daily fallback/reference | Observation age ≤10 calendar days; retrieval age ≤6 hours; cache refresh after 1 hour |

These are indicative simulation inputs, **not real-time dealing quotes**. Original observation and retrieval timestamps remain distinct; provider `stale=false` alone is insufficient. Invalid preferred observations fall back only to independently validated FRED data. If both sources fail their checks, required FX conversion/valuation is unavailable. The preferred cache/backoff is shared within the configured single API worker, not refreshed once per user.

The provider abstraction permits a later replacement without rewriting portfolio accounting or execution history. The preferred key is read only from **`EXCHANGERATE_API_KEY`** on the server. Local `.env` is ignored; templates contain no real credentials. Legacy alternative adapters remain disabled unless explicitly configured with the required rights. No alternative provider is activated by this documentation.

Each execution retains its original reference FX, observation/retrieval metadata, applied conversion rate, amounts, spread and costs. Later valuations use current validated FX without rewriting historical fills. Reconciled attribution distinguishes native investment effects, FX translation, trading costs, conversion costs and rounding when complete execution evidence exists; otherwise attribution is withheld.

Fees are **versioned simulation assumptions**, not universal broker charges or investor-specific tax advice. The current dated policy includes market/instrument/side-specific commissions, applicable simulated transaction/regulatory costs, FX spread and minor-unit rounding. BUY costs enter native cost basis; SELL proceeds are net of costs. Costs already reflected in cash are not deducted twice. Unsupported classifications or expired cost schedules fail closed. The current policy covers 2026 and requires review before trading beyond its validity period. Dividends paid into the simulated account, personal income/capital-gains taxes and certain product/venue charges are not modeled.

See [delayed FX policy](docs/delayed-fx-provider.md), [cost assumptions](docs/realistic-paper-trading-costs.md) and [immutable execution FX / reconciliation](docs/execution-fx-attribution.md).

### Existing demo-account migration

Existing dual-funded accounts are not silently converted or retained as a supported alternative product experience. Schema initialization preserves existing identities and trading records; accounts without a unified root fail closed for unified trading/valuation until the explicit migration is applied.

A separate **once-only admin1/user1 demo-trading reset CLI** is implemented with a private SQLite backup, role/existence checks, one atomic transaction and migration markers. It preserves user IDs, usernames, password hashes, roles and sessions and resets only the authorized Paper Trading data. It uses the same initializer as future users. **It has not been run on the existing admin1/user1 accounts or AWS.** Committing source or starting the API does not execute that reset. See [migration mechanism and maintenance procedure](docs/demo-account-migration.md); do not run it as routine startup.

## Historical conditional portfolio analytics

This deterministic layer reads existing market-specific OOS outputs and current validated snapshots. It does not modify or rerun historical market models, invent sector-risk scores, or infer sectors from company names.

1. **Current Market Stress:** preserve each market's existing regime and validated observation.
2. **Sector / Industry Stress:** select historical OOS observations in the comparable regime, then calculate subsequent 10-trading-day adjusted instrument returns.
3. **Portfolio Exposure:** map verified current holdings by market, sector, industry, currency and individual security using actual USD-equity weights. Unknown classifications remain explicit; currency includes cash.
4. **Stress Sensitivity:** prefer reliable security-level evidence; otherwise allow only an explicitly reviewed same-market sector proxy. Identify the evidence level. Intersect event start/end dates across all holdings before aggregating weighted historical outcomes.
5. **Historical 10D Outlook:** report the empirical portfolio distribution where supportable, separately from **Actual Performance**, which contains only actual recorded valuations.

Sampling selects matching dates chronologically and excludes overlapping 10-session return increments. An instrument needs all 11 valid closes over each window; missing sessions are never filled or compressed. Event selection does not use the subsequent returns. With at least **20 observations**, report median, Q25–Q75, negative-return frequency and dispersion; downside Q10 requires **100 observations**. Smaller samples expose counts and withhold unsupported estimates. Serial dependence remains possible; these cutoffs do not establish significance or calibrated probabilities.

A whole-portfolio range currently requires invested holdings in **one market**, complete evidence and sufficient joint samples. Cash-only accounts receive no stock-return outlook. Portfolios holding both U.S. and Korea securities show separate market contributions; their combined range is withheld until aligned joint-market sampling is supported. Quantiles are never added across independent markets.

Scenarios use current holdings weights, hold current validated FX constant, assume zero cash return and no future trades/additional costs, and use adjusted histories that include instrument distributions. They describe **what historically followed comparable conditions**, not what will happen next. Negative-return frequency is a historical sample proportion, not a guaranteed forecast or future-loss probability. The actual-performance chart does not manufacture history from same-day fills or repeated visits.

See [sampling and analytics contract](docs/conditional-portfolio-analytics.md).

### Current reviewed evidence coverage

The first local research coverage contains **six instruments**, not every sector, industry or listed security:

| Market | Security evidence | Reviewed sector proxy | Industry benchmark |
|---|---|---|---|
| U.S. | NVIDIA — `NVDA` | Technology — `XLK` | Semiconductors — `SOXX` |
| Korea | SK hynix — `000660.KS` | KODEX IT — `266370.KS` | KODEX semiconductor — `091160.KS` |

The October 15, 2026 local collection used valid histories through October 14. U.S. histories start in 2006; Korea coverage varies by instrument/inception. Missing Korean ETF observations remain missing and reduce eligible samples. No pre-inception index history is spliced onto funds.

The collector reuses canonical Symbol Master identities, structured provider classifications and issuer-reviewed fund mandates, with explicit split/dividend-adjusted prices. Receipts preserve source, identity, retrieval/review timestamps, adjustment checks, coverage, review scope and SHA-256 hashes. The importer validates complete bundles and atomically publishes each market independently; failed imports preserve installed evidence. There is no automatic evidence collector on API startup or in the market refresh scheduler.

Current classifications are not a historical point-in-time taxonomy. ETF mandates are proxy evidence, not a full holdings look-through. Industry benchmarks are descriptive context, not implicit security substitutes. Corporate-action checks/spot checks do not independently certify every vendor action. Other holdings, including uncovered common stocks, can trade if valid quotes exist while their analytics remain unavailable. One uncovered holding can block the joint portfolio distribution.

**The evidence files, raw receipts, local numerical reports and disposable QA data are private, Git-ignored local artifacts. They are not supplied by cloning the repository and are not included in the staging artifact manifest.** Missing reviewed evidence produces unavailable analytics, not placeholder numbers. See [sources and evidence lifecycle](docs/real-stress-evidence.md) and [verification scope](docs/real-stress-evidence-results.md).

## Data and licensing boundaries

The application uses existing Yahoo Finance/yfinance, FRED, KRX/ECOS and listing-directory integrations for their respective purposes. Data availability, attribution, access conditions and vendor revisions remain source-specific. Public code, possession of an API key and non-commercial intent do **not** independently establish public display, redistribution, permanent retention or derived-data rights for every source.

The reviewed analytics bundles explicitly retain **`public_display_rights=not_confirmed`** and a local non-commercial research/demo scope. Yahoo/yfinance research/personal-use notices are not treated as authorization for a public multi-user service. Issuer mandate documents do not grant general rights over index histories or commercial classification systems. Keep private evidence out of Git and deployment bundles until appropriate rights or a licensed substitute are established.

The approved exchangerate.dev Free choice is for this non-commercial demo, with provider attribution and delayed wording. It is not a blanket commercial/public redistribution license; verify applicable terms and quota before a different deployment/use. FRED remains a delayed reference subject to its source terms. No guarantee of uninterrupted access, tick-level execution quality or universal public-deployment permission is made.

## Architecture

```text
Next.js / React / TypeScript bilingual dashboard
    ├─ Market pages, U.S./Korea comparison, validation and methodology
    └─ Authenticated Paper Trading + deterministic portfolio analytics
             │ same-origin API proxy
FastAPI (single API worker)
    ├─ Independent validated U.S./Korea snapshots + snapshot-bound SHAP
    ├─ Optional market refresh scheduler / durable job ledger
    ├─ Symbol Master → validated completed-close quotes
    ├─ Unified account → settlement previews → atomic simulated orders
    ├─ FX provider abstraction → shared cache → immutable execution evidence
    └─ OOS + reviewed adjusted histories → conditional analytics
             │
Persistent data: operations ledger/snapshots; private account SQLite;
Symbol Master; reviewed evidence/receipts; approved historical artifacts
Frozen models: independently versioned/verified, mounted read-only on AWS
```

| Path | Responsibility |
|---|---|
| `src/operations/` | Calendar/publication-aware refresh, validation, snapshot publication and scheduler |
| `src/explainability/attribution.py` | Frozen-model, exact-row attribution and consistency checks |
| `src/korea/`, `src/features/`, `src/models/` | Existing independent research/model/feature implementations |
| `src/paper/` | Identity-preserving account storage, discovery, quotes, unified accounting, FX, costs and analytics |
| `src/admin/` | Explicit account/admin, audit, demo migration and reviewed-evidence operator CLIs |
| `frontend/src/app/` | Bilingual UI and same-origin proxies |
| `deploy/`, `scripts/staging_state.py` | Compose/Caddy deployment, artifact manifests, verification and backup tooling |
| `tests/`, `frontend/tests/` | Backend regression and deterministic frontend tests |

Representative endpoints:

| Scope | Endpoints |
|---|---|
| Health/current data | `/health`, `/api/latest`, `/api/korea/latest`, `/api/data-health` |
| Explanation/history/validation | `/api/shap`, `/api/historical`, `/api/validation`, `/api/multi-horizon-validation`; Korea equivalents `/api/korea/shap`, `/api/korea/historical`, `/api/korea/validation` |
| Accounts | `/api/auth/register`, `/api/auth/login`, `/api/auth/me`, `/api/auth/logout` |
| Owner-scoped portfolio | `/api/paper/investment`, `/api/paper/securities`, `/api/paper/quote`, `/api/paper/settlement`, `/api/paper/orders`, `/api/paper/fx`, `/api/paper/fx-ledger`, `/api/paper/stress-analytics` |

Browser workspace requests use `/api/workspace/...`; the Next.js proxy forwards approved paths to the API. Authentication, ownership, CSRF and admin-role authorization remain server-side concerns.

## Local evaluation

Use Python 3.14 (matching the API Docker runtime) and the Node version specified by `frontend/package.json`/the frontend Dockerfile. Development dependencies are in `requirements.txt`; the API image uses hash-locked `requirements-staging.lock`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci
```

A checkout alone is not a complete data environment. Restore approved historical/OOS artifacts, the required frozen models and a validated operations context using the documented artifact workflow. Do not run a training pipeline as an application startup step or overwrite frozen weights to populate missing data.

Configure server-only credentials in the ignored repository-root `.env` or process environment. Relevant names are `PAPER_SESSION_SECRET` (stable, at least 32 characters), `PAPER_ALLOWED_ORIGINS`, `FRED_API_KEY`, `KRX_API_KEY`, `ECOS_API_KEY` and `EXCHANGERATE_API_KEY`. `PAPER_DB_PATH` and `MARKET_OPERATIONS_DIR` select account and operations storage. `MARKET_DATA_ROOT`/`MARKET_MODELS_ROOT` select artifact roots. Use exact allowed origins; secure cookies are required on staging HTTPS. Never put secrets in Git, `NEXT_PUBLIC_*`, URLs, command arguments or screenshots.

For isolated evaluation, select a **new disposable `PAPER_DB_PATH`** and an isolated validated `MARKET_OPERATIONS_DIR` before starting the API. Use `APP_ENV=development`, appropriate local origins and `PAPER_COOKIE_SECURE=false` for local HTTP only. Keep the local scheduler disabled unless intentionally testing it. Existing usernames do not need to be reset to create new disposable test users.

```bash
# Terminal 1: uses the configured server environment and approved artifacts
.venv/bin/python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1

# Terminal 2
API_INTERNAL_URL=http://127.0.0.1:8000 npm --prefix frontend run dev
```

Open `http://localhost:3000/paper-trading`. Required current inputs and reviewed evidence determine which analytics are available. A missing/expired data environment is not repaired by hardcoding dates or examples. [Evidence collection/import commands](docs/real-stress-evidence.md) are explicit operator actions for the bounded reviewed universe; they are not automatic installation steps or a grant of data-use rights.

## AWS / Docker Compose structure

Staging uses [deploy/docker-compose.staging.yml](deploy/docker-compose.staging.yml): a FastAPI API container, a standalone Next.js frontend and Caddy HTTPS proxy. Both API and frontend images require a rebuild for this implementation; restarting old images does not install new code. AWS has not been updated by the local implementation/QA work.

- Environment file: **`/etc/market-stress/staging.env`**; only the empty [template](deploy/staging.env.example) belongs in Git.
- Host `STAGING_ROOT`: **`/srv/market-stress`**, with persistent data on its bind-mounted `data/` directory.
- API database: **`/app/data/paper/workspace.sqlite3`**, persisted as **`/srv/market-stress/data/paper/workspace.sqlite3`**.
- Operations state: `/app/data/operations`; frozen models: read-only `/app/models` from the host's `models/` directory.
- An approved manifest-backed `STAGING_ARTIFACT_BUNDLE` is required for the API build's named artifact context; the initializer validates/installs expected data without treating an empty bind mount as a complete deployment.
- Application processes run as non-root with read-only container filesystems, explicit writable persistent volumes and temporary storage. The single API worker preserves the existing embedded scheduler/cache coordination assumptions.

A safe configuration-only check, from the repository directory, is:

```bash
sudo docker compose --env-file /etc/market-stress/staging.env \
  -f deploy/docker-compose.staging.yml config --quiet
```

Do not print rendered environment configuration or secrets. Actual image rebuild, artifact delivery, backups, schema compatibility, the separately approved demo migration, provider configuration/rights and scheduler health checks belong to an approved deployment maintenance procedure. Private research evidence is not automatically deployable with the code. See [AWS staging guide](docs/aws-ec2-staging.md), [artifact delivery](docs/korea-artifact-deployment.md) and [demo migration](docs/demo-account-migration.md).

## Validation and current evaluation status

```bash
.venv/bin/python -m pytest tests -q
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
git diff --check
```

Use `tests/` for the backend regression suite: legacy `src/korea/test_*_api.py` files are live provider probes, not offline regression tests. Provider-boundary regression fixtures are deterministic and use disposable databases; they never reset real users. A supported local alternative when Turbopack's temporary worker port is blocked is `npm --prefix frontend run build -- --webpack`. Browser QA used the standalone production output with its static/public assets, matching the container packaging structure.

The local browser pass on October 15, 2026 covered desktop 1440/1640px and responsive 390px layouts, English/Korean presentation, real NVDA/SK hynix paths, unified cross-market holdings, explicit FX/cost review, FRED failover and uncovered-security behavior. Private screenshots/runtime accounts remain excluded from Git. Physical mobile keyboards, Safari/Firefox and genuine multi-day performance remain further checks. Recheck the U.S. positive-state presentation once required upstream observations become current; the freshness guard intentionally withheld it after the publication boundary.

No model retraining/recalibration, AWS deployment or existing admin1/user1 reset was performed for this local implementation. Source readiness is separate from data licensing and deployment readiness.

## 한국어 요약

미국과 한국의 **독립적인 시장 스트레스 조기경보**를 실제 모의 포트폴리오 노출 및 과거 조건부 분석과 연결하는 비상업용 연구·데모 프로젝트입니다. 각 시장의 MSI·17개 특성·모델·경고 기준을 유지하고, 향후 **10거래일**의 광범위한 시장 스트레스 신호를 제공합니다. 개별 종목 주가 예측, 보장된 전망 또는 투자 추천 서비스가 아닙니다.

모든 신규 사용자는 USD 기준 총 **$100,000**, USD 현금 **$100,000**·KRW 현금 **₩0**인 하나의 포트폴리오로 시작합니다. 미국·한국 통합 검색, 명시적 환전과 비용, 변경되지 않는 체결 FX 이력을 사용합니다. 관리자도 같은 자본·거래·분석 기능을 사용하며 유료 등급 차별은 없습니다.

시장 스트레스 → 업종/산업 스트레스 → 내 노출 → 과거 스트레스 민감도 → 과거 조건부 10거래일 시나리오를 구분합니다. 검토된 근거는 현재 미국 3개·한국 3개 상품으로 제한되며, 미확인 분류·표본 부족·최신성 미충족 시 분석을 제공하지 않습니다. exchangerate.dev는 약 15분 지연, FRED는 지연 일별 대체·참고 자료입니다. 연구 데이터의 공개 표시·재배포 권한은 별도 확인 대상이며 로컬 검증 승인이나 API 키 보유가 공개 배포 허가를 뜻하지 않습니다.
