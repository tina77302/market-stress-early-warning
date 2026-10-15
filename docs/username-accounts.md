# Username demo accounts

After deploying this version, create the two accounts inside the API container
using an interactive terminal. From `/opt/market-stress-early-warning` on AWS:

```bash
sudo docker compose --env-file /etc/market-stress/staging.env \
  -f deploy/docker-compose.staging.yml exec api \
  python -m src.admin.create_admin --username admin1

sudo docker compose --env-file /etc/market-stress/staging.env \
  -f deploy/docker-compose.staging.yml exec api \
  python -m src.admin.create_user --username user1
```

Do not use `exec -T`, pipes, password arguments, or password environment variables.
Each command requires a terminal and asks for a hidden password twice. Use
14–128 characters. The commands never print the password. If hidden input is
unavailable, confirmation fails, or the user ID already exists, creation fails
without replacing a password, changing a role, or resetting a portfolio.

`admin1` is explicitly created with persisted `role=admin`; `user1` with
`role=user`. There is no role flag on signup/login and no username-based grant.
User IDs are case-insensitive, normalized to lowercase, 3–40 ASCII characters,
start with a letter/digit, and otherwise permit letters/digits/dots/underscores/
hyphens. `@` is reserved for email login so the two identity spaces do not
collide. Each account receives its own USD and KRW Paper Trading portfolios.
No accounts are created automatically by deploying these changes.

Log in at `/paper-trading` using **Email or User ID / 이메일 또는 사용자 ID**.
Email/password login and email signup continue to work. Existing
`create_admin --email ...` behavior and explicit email promotion remain
compatible; the new username creation path never promotes existing accounts.
Admin labels are **Administrator / 관리자** and **User / 일반 사용자**.

## Migration and deployment

Back up the existing account SQLite database using the SQLite backup mechanism
before upgrading, retaining its protected file permissions. Back up/restore
`PAPER_DB_PATH` as configured in the container; do not substitute a new empty
database. Preserve the existing session secret and volume mounts. For the first
upgrade, briefly stop API access/refresh workers and run the updated CLI or
start only the updated API so old and new application versions do not write
concurrently during migration.

On first database access the backward-compatible migration adds nullable
`users.username` with a case-insensitive unique index and permits nullable
`users.email` for username-only accounts. SQLite requires a transactional rebuild
of the users table to remove the legacy email NOT NULL constraint. Existing
numeric IDs, email addresses, roles, password hashes, creation times, sessions,
quotes, portfolios, positions, orders, snapshots, and audit records are preserved.
Foreign-key consistency is checked before commit. Final-admin guards are
reinstalled within that same transaction; failure rolls the migration back.
Repeated migration/startup is safe. Existing accounts keep username NULL and
can continue using email. New username accounts have email NULL, not a fabricated
address. No existing administrator is silently demoted or removed.

The Dockerfile already copies the entire `src/admin` and `src/paper` packages,
so the new CLI and account module are included without a packaging change.
After the migration has run, the previous backend version is not a supported
rollback target for username-only identities; restore the pre-upgrade backup
if a complete rollback is required.

## Ownership and authorization

Sessions and every ordinary Paper Trading endpoint continue to use the stable
numeric user ID. The visible username and persisted role are independent.
Both administrator and normal user see and trade only their own balances,
positions, orders, P&L, and recorded performance. Admin permission does not
bypass ordinary portfolio ownership. Existing admin views remain read-only and
protected by a fresh database role lookup on each request. Session cookies,
origin checks, throttling, CSRF protection, final-admin deletion/demotion guards,
and financial calculations are unchanged.
