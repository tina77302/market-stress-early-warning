# Simulated account workspace

This module is independent of all existing market models and data pipelines. It never sends an order to a broker. The supported-security catalog contains ordinary shares and unleveraged ETFs; the simulation supports only whole-share buys/sells.

## Running locally

1. Install runtime dependencies from `requirements.txt`. For integration tests, also install `requirements-dev.txt`.
2. Configure `PAPER_SESSION_SECRET` in the backend environment or ignored root `.env`; use a random secret of at least 32 characters. The initial local setup generates a private secret without publishing it.
3. Start FastAPI as before: `.venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8000`.
4. Start Next.js with the existing scripts. `/paper-trading` uses the same-origin `/api/workspace/*` proxy. For a separate backend host, set **frontend server-only** `API_INTERNAL_URL`; never use `NEXT_PUBLIC_` for secrets.
5. Sign up using the workspace. Each account receives two independent configurable virtual cash books: `PAPER_STARTING_USD` (default 100,000) and `PAPER_STARTING_KRW` (default 100,000,000). There is no FX conversion, consolidated cross-currency total, or cash transfer.

Stop a running frontend before rebuilding its `.next` directory. Restart after the build to avoid serving stale CSS asset references.

## Storage and authentication

SQLite lives at `PAPER_DB_PATH` (default `data/paper/workspace.sqlite3`, ignored by Git). Keep this directory on persistent storage and back it up. Schema initialization is idempotent; future changes require explicit migrations.

Tables:

- `users`: ID, unique normalized email, salted scrypt password hash, creation timestamp.
- `sessions`: HMAC digest of opaque session token, owning user, absolute expiry. Raw session tokens exist only in HttpOnly cookies.
- `portfolios`: user, market/currency, integer starting cash/current cash, realized P&L, revision, creation date; unique user/market.
- `positions`: portfolio, symbol, positive whole-share quantity, integer total cost basis. Average cost is derived from cost basis/quantity.
- `quotes`: user-scoped quote ID, market/symbol, integer mark and previous close, provider timestamp, fetch time, two-minute expiry.
- `orders`: user/portfolio, idempotency key, security, side, quantity, integer fill, realized P&L, price observation, execution time. User/key is unique.
- `snapshots`: actual observed portfolio/cash values and timestamps.
- `login_attempts`: short-window authentication throttling records.

Registration creates both portfolios atomically and signs in. Login rotates the session. Logout deletes the server session and cookie. Sessions expire after seven days. Portfolio endpoints derive ownership exclusively from the session, never a caller-provided user/portfolio ID. Password hashes and secrets are never returned.

POST requests require an allowed Origin; authenticated writes also require a session-bound CSRF token. The Next.js proxy requires same-origin JSON requests. Authentication attempts are throttled by normalized email and backend peer address. The proxy peer limit is shared for users behind the same proxy.

For HTTPS deployment set `PAPER_COOKIE_SECURE=true`, configure `PAPER_ALLOWED_ORIGINS` with the exact frontend origin, provide the secret through the runtime environment, and protect access to the database and internal backend. The MVP has no email verification, password recovery, MFA, or distributed rate limiting; these are subsequent account features.

## Pricing and orders

Existing yfinance/Yahoo infrastructure supplies raw daily closes (`auto_adjust=False`). Only bars **before today's calendar date in the exchange timezone** are eligible, deliberately excluding today's potentially incomplete bar. Marks are labeled completed daily closes, never real-time. The default freshness limit is five calendar days (`PAPER_MAX_PRICE_AGE_DAYS`). Price failure or stale/non-finite/non-positive values prevent quote issuance/fills. Missing marks make aggregate value/returns unavailable; cash and cost basis remain visible.

The UI requests an expiring server quote, reviews an immutable whole-share order, then submits it with a UUID idempotency key. The server ignores client estimates and looks up the owned quote. A SQLite `BEGIN IMMEDIATE` transaction validates cash/shares, updates cash/cost basis/realized P&L, and appends the order. An identical retried request returns the original fill even after quote expiry; reusing a key for a different request returns a conflict. The client preserves uncertain submissions in sessionStorage, scoped by user and market, for safe retry.

All accounting uses integer cents (USD) or won (KRW). Partial sales allocate average cost proportionally with half-up rounding to one minor unit; a full exit consumes the entire remaining basis. No fees, dividends, stock-split processing, market hours matching, order queue, slippage, or liquidity model are simulated. Daily-close fills are practice accounting, not an executable-market backtest. Positions affected by corporate actions require a future reconciliation feature.

Portfolio history records actual observations since account creation, not fabricated prior returns. Today's P&L is the change since the last actual snapshot before the current UTC day, using completed-close marks; it is unavailable until that baseline exists. It is not live intraday P&L. Portfolio revisions prevent recording a snapshot across a concurrent fill. History currently returns the latest 200 orders and 500 valuations.

## API boundaries

Auth: `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`.

Authenticated paper APIs: `GET /api/paper/securities?market=&q=`, `GET /api/paper/quote?market=&symbol=`, `GET /api/paper/portfolio?market=`, `GET /api/paper/positions?market=`, `GET /api/paper/orders?market=`, `POST /api/paper/orders`, `GET /api/paper/performance?market=`.

All public market-intelligence APIs remain unchanged. Portfolio summary exposes holdings, cash, realized/unrealized P&L, and same-currency allocation. These boundaries can support a future Advisor; no Advisor is implemented. Public market-level stress signals are context, never security-specific recommendations.

## Validation

`pytest tests/test_paper_workspace.py` uses isolated temporary databases and explicit test-only price fixtures. It covers registration/login/logout, password hashing, sessions/CSRF/origin guards, ownership isolation, buy/sell constraints, integer cost/P&L accounting, malformed orders, quote expiry/unavailability, Korean currency accounting, and concurrent idempotency/overspending.

Run frontend TypeScript/build checks with the existing scripts. Keep TypeScript's incremental build information outside the tracked file when validating local UI work.
