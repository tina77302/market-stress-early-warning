"""Reset only an existing account's password using hidden terminal input."""
import argparse
import getpass
import os
import sqlite3
import sys
import warnings
from contextlib import closing
from pathlib import Path

from src.config import DATA_DIR
from src.paper.auth import password_hash


def main(argv=None):
    class SecureParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'Invalid command options. Passwords are accepted only through hidden prompts.\n')

    parser = SecureParser(description='Reset an existing account password without changing identity, role, portfolios or sessions.', allow_abbrev=False)
    parser.add_argument('--username', required=True, help='Existing user ID.')
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        print('Use an interactive terminal; password input through pipes is disabled.', file=sys.stderr)
        return 1
    try:
        path = Path(os.getenv('PAPER_DB_PATH', str(DATA_DIR / 'paper/workspace.sqlite3'))).resolve()
        # mode=rw refuses missing databases. Do not run initialization/migrations
        # or create directories as a side effect of a password reset.
        with closing(sqlite3.connect(path.as_uri()+'?mode=rw', uri=True, timeout=15)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            username = args.username.strip().lower()
            user = db.execute('SELECT id,username,password_hash FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone()
            if not user:
                print('User ID not found. No account changed.', file=sys.stderr)
                return 1
            # No write lock is held while the operator enters the password.
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                password = getpass.getpass('New password (8–128 characters): ')
                confirmed = getpass.getpass('Confirm new password: ')
            if password != confirmed:
                print('Passwords do not match. No account changed.', file=sys.stderr)
                return 1
            if not 8 <= len(password) <= 128:
                print('Use a password of 8–128 characters. No account changed.', file=sys.stderr)
                return 1
            encoded = password_hash(password)
            db.execute('BEGIN IMMEDIATE')
            updated = db.execute('UPDATE users SET password_hash=? WHERE id=? AND username=? COLLATE NOCASE AND password_hash=?',
                                 (encoded, user['id'], user['username'], user['password_hash']))
            if updated.rowcount != 1:
                db.rollback()
                print('Account changed during password input. Retry; no password was overwritten.', file=sys.stderr)
                return 1
            db.commit()
        print('Password reset. Account identity, role, portfolios, history and existing sessions preserved.')
        return 0
    except getpass.GetPassWarning:
        print('Hidden password input is unavailable. No account changed.', file=sys.stderr)
        return 1
    except (sqlite3.Error, OSError, RuntimeError, ValueError):
        print('Unable to reset password. Check the existing database and account configuration. No reset was completed.', file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled. No password was changed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
