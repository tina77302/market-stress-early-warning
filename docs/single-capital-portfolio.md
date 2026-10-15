> Historical implementation notes: the earlier FRED-only, zero-cost and unavailable-FX-attribution descriptions below are superseded by [the current delayed FX policy](delayed-fx-provider.md), [cost policy](realistic-paper-trading-costs.md), and [execution reconciliation](execution-fx-attribution.md). See the [current project overview](../README.md) for browser QA and deployment boundaries. Earlier test counts describe their original implementation stage.

> FX execution evidence, the optional timestamped primary provider, and reconciled attribution now follow [execution FX and portfolio outcomes](execution-fx-attribution.md). This supersedes the earlier unavailable-attribution limitation.

> Cost/spread assumptions are now specified by [the versioned realistic trading policy](realistic-paper-trading-costs.md); that policy supersedes earlier zero-cost assumptions below.

# One user, one USD-base investment portfolio

## Existing data and deployment boundary

The previous schema has `portfolios UNIQUE(user_id, market)` with independent `starting_cash`, `cash`, native-unit positions/cost basis, realized P&L, orders, quotes and snapshots. USD amounts are integer cents; KRW amounts are integer won. The previous default provisioned USD 100,000 AND KRW 100,000,000. That is not one USD 100,000 contribution.

The local `data/paper/workspace.sqlite3` was inspected read-only. It contains zero users/portfolios/positions/orders/snapshots and predates the username schema. It is NOT the AWS database. AWS admin1/user1 IDs, cash, positions and history cannot be inferred from this local file. The AWS bind-mounted database is `/srv/market-stress/data/paper/workspace.sqlite3` (inside API: `/app/data/paper/workspace.sqlite3`). No local or AWS account balances have been reset or migrated by this implementation.

### Read-only AWS inventory, usable with the existing deployed image

Run from the repository directory. This prints only whitelisted account/financial metadata; it never selects password hashes, sessions or secrets and never invokes startup/schema initialization:

```bash
sudo docker compose --env-file /etc/market-stress/staging.env -f deploy/docker-compose.staging.yml exec -T api python - <<'PY'
import json, os, sqlite3
from pathlib import Path
path = Path(os.environ['PAPER_DB_PATH']).resolve()
with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
    db.row_factory = sqlite3.Row
    result = []
    for user in db.execute("SELECT id,username,role FROM users WHERE username IN ('admin1','user1')"):
        records = []
        for leg in db.execute('SELECT id,market,currency,starting_cash,cash FROM portfolios WHERE user_id=?', (user['id'],)):
            record = dict(leg)
            for table in ['positions','orders','snapshots']:
                record[table+'_count'] = db.execute(f'SELECT COUNT(*) FROM {table} WHERE portfolio_id=?', (leg['id'],)).fetchone()[0]
            records.append(record)
        result.append({**dict(user),'native_subledgers_minor_units':records})
    print(json.dumps({'path':str(path),'accounts':result,'mode':'READ_ONLY'},indent=2))
PY
```

Expected: admin1 role=admin, user1 role=user, their actual original IDs, USD/KRW native balances and position/order/snapshot counts. Empty/missing identities require investigation; never create replacement users automatically. A reusable equivalent CLI `python -m src.admin.audit_portfolios` is also added locally, but is not available in an old deployed image until an approved rebuild.

## Implemented architecture

`investment_accounts` has one primary-key row per user with initial USD capital fixed at 10,000,000 cents and an actual inception timestamp. Existing `portfolios` rows are native-currency subledgers, not independently funded portfolios. All three provisioning paths (email signup, username CLI and email admin bootstrap) now create USD 100,000 cash and KRW 0. Legacy starting-balance environment overrides no longer create additional capital. Neither promotion nor re-running an account-creation CLI re-funds an existing user.

Schema startup adds FX provenance, quote-to-FX bindings, FX ledger and unified valuation snapshots. The old `starting_cash>0` CHECK is relaxed to `>=0` by a locked transactional table copy with the same columns, IDs, balances, foreign keys and historical rows, followed by `foreign_key_check`. No existing account is automatically enrolled or re-capitalized. Before the explicit demo migration, a missing unified root fails closed for valuation/settlement. Apply the demo migration in the maintenance window before reopening the product; it is not a supported legacy user mode. This schema operation was tested on a legacy database fixture; it has not been applied to AWS.

Native BUY/SELL cost basis, whole-share rules and realized P&L are retained. Per-native-currency return percentages are no longer presented as separate portfolio performance for unified accounts. Legacy native return calculations remain readable unchanged. Global P&L is USD equity minus the single USD 100,000 contribution. Unified history records actual complete valuations only, linked to the exact FX observation used; old independent histories are not spliced into it.

## FX source and validity

Source: Federal Reserve H.10 via FRED DEXKOUS, won per one USD. This uses the project's existing FRED provider/API-key configuration, with no paid service. References:

- https://fred.stlouisfed.org/series/DEXKOUS
- https://fred.stlouisfed.org/docs/api/fred/series_observations.html

Daily dated observations are published with a lag; they are not a guaranteed real-time execution feed. UI: “latest available USD/KRW rate.” Metadata includes immutable rate ID, decimal rate, original observation date, source, UTC retrieval timestamp and AVAILABLE status. Numeric/missing/nonfinite/negative/future values are rejected. Maximum observation age is 10 calendar days, accommodating the H.10 publication lag and weekends; retrieval must be within six hours. Cache is reused for one hour; failed refresh may use LKG only if both validity limits still pass. No stale rate is used for settlement or needed translation. No fallback synthetic or Yahoo rate is substituted. Missing FRED configuration fails explicitly.

## Settlement and rounding

A security quote is still validated by the existing price provider and completed-close safeguards. It is bound to an immutable FX observation when one is available. The existing 120-second stock quote expiry also bounds settlement consent. `GET /api/paper/settlement` checks quote ownership, freshness, native cash and available funding. It returns native order value, base-USD equivalent when available, and the exact proposed source/destination minor units. Korean BUY requires validated FX for USD review even if existing KRW is sufficient.

- Spend existing settlement-currency cash first.
- For a KRW shortfall: USD cents debited = ceil(shortfall KRW * 100 / rate); KRW credited = floor(USD cents * rate / 100).
- For a USD shortfall: KRW debited = ceil(shortfall USD cents * rate / 100); USD cents credited = floor(KRW * 100 / rate).
- Source cash must cover the conversion. No negative balances, borrowing, margin or free KRW.
- USD and Korean SELL proceeds stay in their native currency. A later opposite-currency BUY can use a reviewed shortfall conversion.
- No FX fees/spread are modeled. Explicit discrete-unit rounding may cause small conversion losses; residual cash remains owned by the same portfolio.

The frontend never computes the accounting FX amount: it reviews the server's integer amounts. POST order includes those reviewed amounts. Execution holds `BEGIN IMMEDIATE`, checks current balances, the exact rate and quote freshness again, and rejects any changed/unreviewed conversion. Both currency updates, native position/order and the FX ledger commit together or roll back together. The FX event records source/destination amounts, rate provenance, post-order USD/KRW cash and resulting share quantity. Ledger history is shown in the UI. Accepted request retries return the same order even after quote expiry, and mismatched FX retry intent is rejected. Pending-order storage retains approved FX amounts.

Base USD equity = USD cash + U.S. holdings + (KRW cash + Korean holdings) / validated rate. Missing needed FX/prices returns incomplete totals and records no misleading unified snapshot. With zero KRW exposure, known USD-only equity remains available despite an FX outage. Native investment P&L remains visible; separate investment-vs-FX return attribution is not fabricated. Total USD P&L includes translation and rounding.

## Existing admin1/user1 migration: implemented explicitly, not executed

The final user instruction explicitly authorizes resetting admin1/user1 Paper Trading demo data. The earlier archive-era proposal is superseded by the implemented [one-time demo-account migration](demo-account-migration.md). It preserves identities, credentials, roles and sessions, creates a private backup, and atomically resets only those two accounts through an explicit CLI. It is not run on startup and has not been run on AWS.

## Local verification scope

Tests mock stock and FX provider boundaries. They cover one initial capital, signup/role parity, both search markets, reviewed FX and native-cash reuse, buy/sell/cost basis, reverse conversion, rounding/remainders, exact event provenance, concurrent retry/idempotency, rollback after FX debit, ownership, stale/unavailable FX and incomplete valuation, translation movement, legacy-row preservation, auto quote/QQQ estimate, pending-order recovery, localization and layout rendering. No browser screenshot or live FX/stock execution validation is claimed.


## Review file manifest

Backend production: `src/paper/store.py`, `src/paper/accounts.py`, `src/paper/admin.py` (new-user capital initialization only), `src/paper/router.py`, `src/paper/service.py`, `src/paper/fx.py` (new), `src/paper/investment.py` (new), `src/admin/audit_portfolios.py` (new).

Frontend for this capital change: `frontend/src/app/api/workspace/[...path]/route.ts` (three explicit endpoint allowlist entries only), `frontend/src/app/paper-trading/page.tsx`, `PortfolioWorkspace.tsx`, `TradeTicket.tsx`, `types.ts`, `paper-trading.css` in the same directory, both `frontend/src/app/i18n/{en,ko}.json`, and frontend tests. The prior uncommitted shared-market status, unified `SecurityPicker.tsx`, `workflow.ts`, package test command and compact layout are retained.

Backend tests: `tests/conftest.py` (mock FX boundary), `tests/test_unified_investment.py` (new), `tests/test_paper_workspace.py`, `tests/test_security_discovery.py`, `tests/test_username_accounts.py`, `tests/test_multi_admin.py`. Older native-accounting tests explicitly seed low test balances for their edge cases; these fixtures do not control production provisioning. New tests assert actual provisioning ignores legacy dual-starting-balance overrides and supplies only USD 100,000 and KRW 0.

Final verification: full backend suite 238 passed (two pre-existing warnings); focused trading/discovery/identity/reset suite 124 passed; focused new investment/FX/migration suite 21 passed; bilingual/rendering tests and 38 workflow/proxy regressions passed; TypeScript and production webpack build passed; `git diff --check` passed. Six frozen model files, market operations/explainability code, auth module and reset-password CLI match their pre-change SHA-256 baseline. No browser screenshot was captured. No commit, push, deployment or account reset was performed.
