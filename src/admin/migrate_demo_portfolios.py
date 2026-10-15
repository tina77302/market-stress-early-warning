"""Explicit, once-only reset of the two authorized demo trading accounts.

No startup hook. No arbitrary user selector. Identity and session rows are never
written. A private SQLite backup is made before changing Paper Trading data.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from src.paper.accounts import initialize_portfolio
from src.paper.store import database

VERSION = 'demo-unified-usd-100000-v1'
DEMO_USERS = ('admin1', 'user1')


def migrate_demo_portfolios():
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        users = list(db.execute(
            'SELECT id,username,role FROM users WHERE username COLLATE NOCASE IN (?,?) ORDER BY id',
            DEMO_USERS))
        if {row['username'].lower() for row in users} != set(DEMO_USERS):
            raise ValueError('Both admin1 and user1 must already exist. No account was created or reset.')
        if {row['username'].lower(): row['role'] for row in users} != {'admin1': 'admin', 'user1': 'user'}:
            raise ValueError('Demo account roles do not match. No role or trading data was changed.')
        pending = [row for row in users if not db.execute(
            'SELECT 1 FROM paper_capital_migrations WHERE user_id=? AND version=?',
            (row['id'], VERSION)).fetchone()]
        if not pending:
            return {'status': 'ALREADY_APPLIED', 'accounts': [dict(row) for row in users]}
        # BEGIN IMMEDIATE excludes writers while a separate reader backs up the
        # last committed database. Never backup from the active write connection.
        path = Path(db.execute('PRAGMA database_list').fetchone()['file'])
        backup = path.with_name(path.name + '.before-demo-unified-' + uuid4().hex + '.sqlite3')
        descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source:
                with sqlite3.connect(backup) as destination:
                    source.backup(destination)
        except BaseException:
            backup.unlink(missing_ok=True)
            raise
        created = datetime.now(timezone.utc).isoformat()
        for user in pending:
            user_id = user['id']
            for table in ('paper_fx_ledger', 'paper_order_costs', 'paper_order_previews',
                          'quotes', 'orders', 'investment_snapshots'):
                db.execute(f'DELETE FROM {table} WHERE user_id=?', (user_id,))
            for table in ('positions', 'snapshots'):
                db.execute(f'DELETE FROM {table} WHERE portfolio_id IN '
                           '(SELECT id FROM portfolios WHERE user_id=?)', (user_id,))
            db.execute('DELETE FROM investment_accounts WHERE user_id=?', (user_id,))
            db.execute('DELETE FROM portfolios WHERE user_id=?', (user_id,))
            initialize_portfolio(db, user_id, created)
            db.execute('INSERT INTO paper_capital_migrations VALUES (?,?,?)',
                       (user_id, VERSION, created))
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Migration relationship check failed; all trading changes rolled back.')
        db.commit()
        return {'status': 'APPLIED', 'backup': str(backup), 'accounts': [dict(row) for row in users]}


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        result = migrate_demo_portfolios()
    except (ValueError, RuntimeError, sqlite3.Error, OSError):
        print('Migration failed; no partial trading reset was committed. Check account roles, database permissions and available disk space.')
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
