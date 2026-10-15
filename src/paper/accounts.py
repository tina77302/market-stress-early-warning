"""Trusted CLI-only username provisioning. Web registration always stays role=user."""
import re

from .auth import password_hash
from .service import now_iso
from .store import database, starting_cash


class AccountExistsError(ValueError):
    """A duplicate username must never reset or promote an existing account."""


def provision_username_account(username, password, *, role='user'):
    username = username.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}', username):
        raise ValueError('User ID must be 3–40 ASCII letters, digits, dots, underscores or hyphens; start with a letter or digit.')
    if role not in ('admin', 'user'):
        raise ValueError('Invalid persisted role.')
    if password is None or not 8 <= len(password) <= 128:
        raise ValueError('Use a password of 8–128 characters.')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT id FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone():
            raise AccountExistsError('User ID already exists. No account changed.')
        created = now_iso()
        user = db.execute('INSERT INTO users (username,email,password_hash,created_at,role) VALUES (?,NULL,?,?,?)',
                          (username, password_hash(password), created, role))
        for market, currency in [('us', 'USD'), ('korea', 'KRW')]:
            cash = starting_cash(market)
            portfolio = db.execute('INSERT INTO portfolios (user_id,market,currency,starting_cash,cash,created_at) VALUES (?,?,?,?,?,?)',
                                   (user.lastrowid, market, currency, cash, cash, created))
            db.execute('INSERT INTO snapshots (portfolio_id,observed_at,value,cash) VALUES (?,?,?,?)', (portfolio.lastrowid, created, cash, cash))
        if role == 'admin':
            from .admin import record_admin_activity
            record_admin_activity(db, user.lastrowid, 'admin.bootstrap_created', user.lastrowid)
        db.commit()
    return 'created'
