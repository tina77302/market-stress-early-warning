# Authorized demo-account migration

The final account migration requirement supersedes the earlier archive-era proposal. admin1 and user1 are disposable **trading demo data**, while their identity, login and role records must survive. This implementation resets only their Paper Trading data through an explicit operator command. It does not automatically delete data at startup or on database access.

## Mechanism

Run `python -m src.admin.migrate_demo_portfolios` against the intended `PAPER_DB_PATH`. It accepts no passwords, selectors, arbitrary usernames or force-reset option. It requires both existing usernames, admin1 role=admin and user1 role=user; otherwise it aborts without creating identities or changing roles.

A `BEGIN IMMEDIATE` transaction locks out concurrent writers. Before changing trading rows, a separate SQLite reader takes a consistent backup through the SQLite backup API, including committed WAL data. The backup sits alongside the database, mode 0600, with a unique `.before-demo-unified-<uuid>.sqlite3` suffix. It contains sensitive account records: keep it private, do not print its contents, and retain it under the same protected storage controls as the database. If backup creation fails, no trading reset occurs.

For each demo account not marked with `demo-unified-usd-100000-v1`, the command removes old trading data and calls the **same initializer used for every new normal/admin account**. Both resets and their markers commit together, after a foreign-key check. Any failure rolls back both accounts. Concurrent runs recheck the markers while holding the write lock. Subsequent runs return `ALREADY_APPLIED`, leaving subsequent trades intact. Markers are not a future reset button and must not be manually deleted.

No role-specific accounting paths, privileged market data, different security universes or additional capital are introduced. Ordinary users and admins use the same search, quotes, FX, spreads, fees, validation and execution engine. Existing two `portfolios` rows are internal USD/KRW settlement ledgers belonging to one `investment_accounts` root. They are not two user-facing portfolios. The page has one USD-base equity/return/history and market filters; no separate USD Portfolio/KRW Portfolio selector exists.

## Tables affected

| Table | Effect for admin1/user1 only |
|---|---|
| `positions`, `orders` | Old positions and orders removed |
| `snapshots`, `investment_snapshots` | Old performance removed; current inception snapshots created |
| `quotes` | Old executable references removed, so pending old requests cannot execute |
| `paper_quote_fx`, `paper_quote_costs` | Old quote metadata removed by existing quote cascades |
| `paper_order_previews`, `paper_order_costs` | Old approvals and cost history removed |
| `paper_fx_ledger` | Old user conversion events removed |
| `portfolios` | Recreated as USD cash 10,000,000 cents and KRW cash 0; zero realized P&L |
| `investment_accounts` | Recreated with one USD 100,000 contribution and current inception |
| `paper_capital_migrations` (new) | Per-user version/timestamp records the completed reset |

`users` (including IDs, usernames, password hashes and roles), `sessions`, `login_attempts`, `admin_activity` and shared `paper_fx_rates` are not changed by the reset. No database file is deleted. Unrelated users' trading histories are not reset. Future registered users already receive one USD 100,000 account through the existing common initializer, so they require no reset command.

## Intended AWS procedure after code review and approved image update

No AWS action was performed during implementation. The deployed image must first contain this module; do not run an old image expecting the command to exist. Quiesce Paper Trading requests during the maintenance window and close pending-order screens. Do not disable or modify the market refresh scheduler for this migration.

From the deployed repository directory, with the approved API image running:

```bash
sudo docker compose --env-file /etc/market-stress/staging.env -f deploy/docker-compose.staging.yml exec api python -m src.admin.migrate_demo_portfolios
```

Expected JSON: `status: APPLIED`, private backup path, admin1's original ID/username/admin role and user1's original ID/username/user role. No password prompts or password arguments are involved because credentials are never changed. Re-running reports `ALREADY_APPLIED` and does not reset new trades.

The configured API database is `/app/data/paper/workspace.sqlite3`, bind-mounted from `/srv/market-stress/data/paper/workspace.sqlite3`; the backup is persisted beside it. Do not replace the database file with an empty file or delete the bind mount.

Read-only identity/native-cash verification:

```bash
sudo docker compose --env-file /etc/market-stress/staging.env -f deploy/docker-compose.staging.yml exec api python -m src.admin.audit_portfolios
```

For each account, expected USD cash is 10,000,000 cents and KRW cash 0, zero positions/orders, and fresh initial snapshots. Log in using the unchanged credentials and verify the unified page and authenticated investment endpoint show the state below. Existing sessions remain valid; a stale pending order receives a missing/expired quote response and needs fresh review.

## Resulting state, verified using temporary databases

| Field | admin1 | user1 | Third newly registered user |
|---|---|---|---|
| Role | admin (unchanged) | user (unchanged) | user |
| Base currency | USD | USD | USD |
| Initial capital / total value | $100,000 | $100,000 | $100,000 |
| USD cash | $100,000 | $100,000 | $100,000 |
| KRW cash | ₩0 | ₩0 | ₩0 |
| Positions / orders | none | none | none |
| Realized / unrealized P&L | $0 / $0 | $0 / $0 | $0 / $0 |
| Trading / FX conversion costs | $0 / $0 | $0 / $0 | $0 / $0 |

The tests then execute identical US and Korea transactions for all three users and compare discovery responses, quote/preview fields, commissions, FX, cash, P&L and cumulative costs. Only ownership identifiers differ. user1 remains denied admin functionality, while admin1 retains it. Tests also cover private backup contents, complete user/session preservation, repeat invocation, concurrent invocation, stale old order requests, untouched unrelated trading history and transaction rollback after an injected failure on the second account.

The production AWS states have **not** been changed or verified remotely. Applying the reviewed command there remains an operational step; there is no claim that AWS accounts have already been reset.

## Validation and changed files for this requirement

- Full backend: **268 passed**, 2 existing warnings, 106.79 seconds.
- Focused migration tests, rerun with both-market BUY/SELL parity: **5 passed**, 1 existing Starlette warning.
- Frontend: **40 workflow tests passed**, 1,012 bilingual message checks passed (existing unrelated React list-key warnings).
- TypeScript and production webpack build: passed.
- `git diff --check`: passed.
- Six model checksums and all 23 protected-file hashes: unchanged.
- No commit, push, deployment or production database reset. No screenshots captured.

Exact files changed for this requirement (earlier uncommitted work retained):

```
src/admin/migrate_demo_portfolios.py           new explicit migration command
src/paper/store.py                            migration marker schema only
src/paper/investment.py                       replace legacy-mode error wording
frontend/src/app/i18n/en.json                 matching unified-account error wording
frontend/src/app/i18n/ko.json                 matching unified-account error wording
tests/test_demo_capital_migration.py           migration and three-account parity tests
docs/demo-account-migration.md                procedure, tables, states and validation
docs/single-capital-portfolio.md              superseded migration plan updated
docs/realistic-paper-trading-costs.md          link implemented migration procedure
```
