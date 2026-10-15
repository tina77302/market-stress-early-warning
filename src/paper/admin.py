"""Environment-based owner bootstrap and strictly read-only administration."""
import os
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from .auth import password_hash, require_admin
from .service import now_iso
from .store import database, starting_cash

router = APIRouter(prefix='/api/admin', tags=['Read-only administration'])


def record_admin_activity(db, admin_user_id, action, target_user_id=None):
    """Append audit metadata within the caller's action transaction; never credentials."""
    actor = db.execute('SELECT role FROM users WHERE id=?', (admin_user_id,)).fetchone()
    if not actor or actor['role'] != 'admin':
        raise RuntimeError('Audit actor must be an administrator.')
    if not re.fullmatch(r'[a-z][a-z0-9_.]{0,79}', action):
        raise ValueError('Use a short predefined action identifier, never free-form data.')
    db.execute('INSERT INTO admin_activity (admin_user_id,action,target_user_id,timestamp) VALUES (?,?,?,?)', (admin_user_id, action, target_user_id, now_iso()))


def bootstrap_admin():
    """Legacy single-account environment bootstrap; CLI is preferred for multiple admins."""
    email = os.getenv('ADMIN_EMAIL', '')
    password = os.getenv('ADMIN_PASSWORD', '')
    if not email.strip() and not password:
        return 'not_configured'
    return provision_admin(email, password, promote_existing=os.getenv('ADMIN_BOOTSTRAP_PROMOTE_EXISTING', 'false').lower() == 'true')


def provision_admin(email, password, promote_existing=False):
    """Transactional multi-admin provisioning; never overwrite an existing password."""
    email = email.strip().lower()
    if not (3 <= len(email) <= 254 and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)):
        raise RuntimeError('Invalid admin email configuration.')
    if password is not None and not 8 <= len(password) <= 128:
        raise RuntimeError('Invalid admin password configuration: use 8–128 characters.')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT id,role FROM users WHERE email=?', (email,)).fetchone()
        if existing:
            if existing['role'] == 'admin':
                return 'already_exists'
            if not promote_existing:
                raise RuntimeError('Admin bootstrap conflicts with an existing normal account. Explicit ADMIN_BOOTSTRAP_PROMOTE_EXISTING=true is required to promote it; its password will be preserved.')
            db.execute("UPDATE users SET role='admin' WHERE id=?", (existing['id'],))
            record_admin_activity(db, existing['id'], 'admin.bootstrap_promoted', existing['id'])
            db.commit()
            return 'promoted_password_preserved'
        if password is None:
            raise RuntimeError('Promotion requires an existing account; no account created.')
        created = now_iso()
        user = db.execute("INSERT INTO users (email,password_hash,created_at,role) VALUES (?,?,?,'admin')", (email, password_hash(password), created))
        # An admin's own simulated accounts obey exactly the same ownership/accounting rules.
        for market, currency in [('us', 'USD'), ('korea', 'KRW')]:
            cash = starting_cash(market)
            portfolio = db.execute('INSERT INTO portfolios (user_id,market,currency,starting_cash,cash,created_at) VALUES (?,?,?,?,?,?)', (user.lastrowid, market, currency, cash, cash, created))
            db.execute('INSERT INTO snapshots (portfolio_id,observed_at,value,cash) VALUES (?,?,?,?)', (portfolio.lastrowid, created, cash, cash))
        record_admin_activity(db, user.lastrowid, 'admin.bootstrap_created', user.lastrowid)
        db.commit()
    return 'created'


@router.get('/overview')
def overview(user=Depends(require_admin)):
    now = int(time.time())
    with database() as db:
        db.execute('BEGIN')
        counts = {name: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for name, table in [('total_users', 'users'), ('total_portfolios', 'portfolios'), ('total_simulated_orders', 'orders')]}
        counts['accounts_with_unexpired_sessions'] = db.execute('SELECT COUNT(DISTINCT user_id) FROM sessions WHERE expires_at>?', (now,)).fetchone()[0]
    return {**counts, 'current_account': user, 'health': {'api': 'available', 'database': 'available'}, 'observed_at': datetime.now(timezone.utc).isoformat(), 'session_note': 'Accounts with unexpired sessions, not currently online users.', 'read_only': True}


@router.get('/users')
def users(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), user=Depends(require_admin)):
    with database() as db:
        db.execute('BEGIN')
        total = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        rows = db.execute('SELECT u.id,u.email,u.username,u.role,u.created_at,COUNT(p.id) AS portfolio_count FROM users u LEFT JOIN portfolios p ON p.user_id=u.id GROUP BY u.id ORDER BY u.id LIMIT ? OFFSET ?', (limit, offset)).fetchall()
    return {'data': [{**dict(row), 'portfolio_status': 'present' if row['portfolio_count'] else 'none'} for row in rows], 'total': total, 'limit': limit, 'offset': offset}


@router.get('/data-health')
def data_health(user=Depends(require_admin)):
    from src.operations.service import health
    from src.operations.store import history, database as operations_database
    with operations_database() as db:
        alerts = [dict(row) for row in db.execute('SELECT id,market,job_id,action,created_at,delivered_at FROM alerts ORDER BY id DESC LIMIT 50')]
    return {'markets': {market: health(market) for market in ['us', 'korea']}, 'jobs': history(limit=30), 'alerts': alerts}
