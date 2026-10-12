# Read-only admin accounts

Administration uses the existing login/session system. `users.role` is constrained to `user` or `admin` and defaults to `user`. The SQLite migration adds this column without changing existing passwords, portfolio balances, orders, or sessions. Existing accounts remain normal users.

Every admin API depends on `require_admin`, which reads the role from the database on each authenticated request. Anonymous requests receive 401; authenticated normal users receive 403. Browser role checks control presentation only. Role changes cannot be submitted through signup or the admin APIs.

## Multiple independent administrators

There is no unique-admin constraint or hardcoded owner identity. Any number of accounts can have `role=admin`, with independent salted password hashes, sessions and private portfolios. Normal signup always creates `role=user`.

From the repository root, create each administrator individually:

```bash
.venv/bin/python -m src.admin.create_admin --email "<admin1-email>"
.venv/bin/python -m src.admin.create_admin --email "<admin2-email>"
```

Replace the email placeholders. Each command securely prompts for and confirms that account's password (14–128 characters). Passwords are not echoed, accepted as command arguments, written to files, or printed in logs. Omit `--email` to prompt for the email too. Run in an interactive terminal; piped input and insecure getpass fallback are refused. The command loads the ignored root `.env` to locate the same database as the backend. `PAPER_SESSION_SECRET` must remain configured for normal login.

Log in through `/paper-trading`; each administrator gets **Account → Admin console**. No backend restart is required after command-based creation. Re-running for an existing admin leaves its password, role, portfolios and history unchanged. Adding a second administrator never overwrites the first.

To deliberately promote an existing normal user:

```bash
.venv/bin/python -m src.admin.create_admin --email "<existing-email>" --promote-existing
```

Type `PROMOTE` when asked. Its existing password and portfolios are preserved; no new password is collected. The command refuses to create a nonexistent account in promotion mode.

The previous optional `ADMIN_EMAIL`/`ADMIN_PASSWORD` environment bootstrap remains compatible. It provisions only the named account, imposes no single-admin limit, and never rotates existing passwords on restart. The CLI is preferred so multiple admins do not require persisted bootstrap passwords or a shared password list. Remove legacy bootstrap variables after initial creation if no longer needed; this does not remove accounts. `.env.example` contains blank placeholders only.

## Final administrator protection and audit foundation

SQLite triggers reject deletion or demotion of the final administrator, including direct SQL and concurrent writers using the existing schema. There are still no destructive or role-editing web APIs. These guards protect future privileged capabilities without adding permission levels.

`admin_activity` stores `id`, `admin_user_id`, `action`, optional `target_user_id`, and UTC `timestamp`. Trusted local creation/promotion writes a bootstrap action in the same transaction. Idempotent retries do not duplicate events. Audit IDs are retained independently of future account deletion; the table intentionally has no cascading user foreign keys. Update/delete triggers make application audit records append-only.

`record_admin_activity(db, admin_user_id, action, target_user_id=None)` verifies that the actor is an admin and appends metadata within the caller's transaction. Action identifiers are short predefined terms, never free-form credentials or request bodies. Future privileged actions should call this helper atomically with their changes. No new log UI or destructive admin workflow is implemented.

## Read-only endpoints

- `GET /api/admin/overview`: user, portfolio and simulated-order counts; distinct accounts with unexpired sessions; current authenticated admin identity; API/database availability.
- `GET /api/admin/users?limit=50&offset=0`: paginated ID, email, role, creation date and portfolio existence/count. Limit is capped at 100.

Responses are not cached and never expose passwords, hashes, session tokens or CSRF tokens. Unexpired sessions indicate valid sessions, not currently online users. Health describes the successful current API/database request, not market-data source freshness.

The Next.js same-origin workspace proxy forwards the two admin endpoints. The global account menu checks `/api/auth/me`; only an authenticated administrator receives the Admin console link. Public market pages remain accessible. `/admin` is a public shell with protected data; it displays a login/access-required state when authorization fails.

Admin roles do not grant paper-trading impersonation. All portfolio/order ownership checks continue to use the signed-in account ID. Admin statistics are aggregate/read-only; admins trade only in their own ordinary virtual portfolios.

## Verification

`tests/test_admin_workspace.py` covers legacy migration, explicit promotion, preserved hashes, duplicate-free startup/restart, normal-user 403, anonymous 401, admin read access, role revalidation, response redaction, blocked signup escalation, and credential-safe errors/logs. Tests also cover multiple independent admins, separate passwords, secure command prompts, final-admin SQL/concurrency guards, and append-only activity. No role-changing or destructive admin endpoints are exposed.
