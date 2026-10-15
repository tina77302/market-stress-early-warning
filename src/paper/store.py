import os
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from src.config import DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, email TEXT UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL,
 username TEXT COLLATE NOCASE,
 role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin'))
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS portfolios (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), market TEXT NOT NULL,
 currency TEXT NOT NULL, starting_cash INTEGER NOT NULL CHECK(starting_cash>0),
 cash INTEGER NOT NULL CHECK(cash>=0), revision INTEGER NOT NULL DEFAULT 0, realized_pnl INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
 UNIQUE(user_id, market)
);
CREATE TABLE IF NOT EXISTS positions (
 portfolio_id INTEGER NOT NULL REFERENCES portfolios(id), symbol TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity>0), cost_basis INTEGER NOT NULL CHECK(cost_basis>=0),
 PRIMARY KEY(portfolio_id, symbol)
);
CREATE TABLE IF NOT EXISTS quotes (
 id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), market TEXT NOT NULL, symbol TEXT NOT NULL,
 price INTEGER NOT NULL CHECK(price>0), previous_close INTEGER, observed_at TEXT NOT NULL,
 fetched_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
 id INTEGER PRIMARY KEY, portfolio_id INTEGER NOT NULL REFERENCES portfolios(id), user_id INTEGER NOT NULL REFERENCES users(id),
 request_key TEXT NOT NULL, market TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
 quantity INTEGER NOT NULL CHECK(quantity>0), execution_price INTEGER NOT NULL CHECK(execution_price>0),
 realized_pnl INTEGER NOT NULL, quote_id TEXT NOT NULL, price_observed_at TEXT NOT NULL, executed_at TEXT NOT NULL,
 UNIQUE(user_id, request_key)
);
CREATE TABLE IF NOT EXISTS snapshots (
 id INTEGER PRIMARY KEY, portfolio_id INTEGER NOT NULL REFERENCES portfolios(id), observed_at TEXT NOT NULL,
 value INTEGER NOT NULL, cash INTEGER NOT NULL, UNIQUE(portfolio_id, observed_at)
);
CREATE TABLE IF NOT EXISTS admin_activity (
 id INTEGER PRIMARY KEY, admin_user_id INTEGER NOT NULL, action TEXT NOT NULL,
 target_user_id INTEGER, timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS admin_activity_actor_time ON admin_activity(admin_user_id,timestamp);
CREATE TABLE IF NOT EXISTS login_attempts (key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start INTEGER NOT NULL);
"""


FINAL_ADMIN_GUARDS = (
    """CREATE TRIGGER IF NOT EXISTS protect_final_admin_demotion
    BEFORE UPDATE OF role ON users
    WHEN OLD.role='admin' AND NEW.role!='admin' AND (SELECT COUNT(*) FROM users WHERE role='admin')<=1
    BEGIN SELECT RAISE(ABORT,'Cannot demote the final administrator'); END;""",
    """CREATE TRIGGER IF NOT EXISTS protect_final_admin_deletion
    BEFORE DELETE ON users
    WHEN OLD.role='admin' AND (SELECT COUNT(*) FROM users WHERE role='admin')<=1
    BEGIN SELECT RAISE(ABORT,'Cannot delete the final administrator'); END;""",
)


def factor(market):
    return 100 if market == 'us' else 1


def starting_cash(market):
    name, default = ('PAPER_STARTING_USD', '100000') if market == 'us' else ('PAPER_STARTING_KRW', '100000000')
    amount = Decimal(os.getenv(name, default)) * factor(market)
    if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value() or amount > 10**14:
        raise ValueError(f'Invalid {name}')
    return int(amount)


def migrate_login_identity(connection):
    """Preserve primary keys and foreign keys while permitting username-only users.

    SQLite cannot drop NOT NULL in place. Rebuild just users in one locked
    transaction with FK enforcement temporarily off on this connection only.
    References continue to name users; no rename of the old table is performed.
    """
    columns = {row['name']: row for row in connection.execute('PRAGMA table_info(users)')}
    if 'username' in columns and not columns['email']['notnull']:
        return
    connection.execute('PRAGMA foreign_keys=OFF')
    try:
        connection.execute('BEGIN IMMEDIATE')
        columns = {row['name']: row for row in connection.execute('PRAGMA table_info(users)')}
        if columns['email']['notnull']:
            connection.execute("""CREATE TABLE users_identity_migration (
                id INTEGER PRIMARY KEY, email TEXT UNIQUE, password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL, username TEXT COLLATE NOCASE,
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin'))
            )""")
            username = 'username' if 'username' in columns else 'NULL'
            connection.execute(f'INSERT INTO users_identity_migration (id,email,password_hash,created_at,username,role) SELECT id,email,password_hash,created_at,{username},role FROM users')
            connection.execute('DROP TABLE users')
            connection.execute('ALTER TABLE users_identity_migration RENAME TO users')
        elif 'username' not in columns:
            connection.execute('ALTER TABLE users ADD COLUMN username TEXT COLLATE NOCASE')
        for guard in FINAL_ADMIN_GUARDS:
            connection.execute(guard)
        if connection.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Identity migration failed relationship integrity check.')
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.execute('PRAGMA foreign_keys=ON')


@contextmanager
def database():
    path = Path(os.getenv('PAPER_DB_PATH', str(DATA_DIR / 'paper/workspace.sqlite3')))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA journal_mode=WAL')
    connection.executescript(SCHEMA)
    # Upgrade existing accounts without changing passwords, portfolios or sessions.
    if 'role' not in {row['name'] for row in connection.execute('PRAGMA table_info(users)')}:
        connection.execute('BEGIN IMMEDIATE')
        # Recheck after obtaining the lock, since another worker may have migrated it.
        if 'role' not in {row['name'] for row in connection.execute('PRAGMA table_info(users)')}:
            connection.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin'))")
        connection.commit()
    migrate_login_identity(connection)
    for guard in FINAL_ADMIN_GUARDS:
        connection.execute(guard)
    # Install after the legacy role migration; database guards survive concurrent writers.
    connection.executescript("""
    CREATE UNIQUE INDEX IF NOT EXISTS users_username_unique ON users(username COLLATE NOCASE);
    CREATE TRIGGER IF NOT EXISTS protect_admin_activity_update
    BEFORE UPDATE ON admin_activity BEGIN SELECT RAISE(ABORT,'Admin activity is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS protect_admin_activity_delete
    BEFORE DELETE ON admin_activity BEGIN SELECT RAISE(ABORT,'Admin activity is append-only'); END;
    """)
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
