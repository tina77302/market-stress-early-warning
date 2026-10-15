"""Create independent admins with hidden terminal input, never password arguments."""
import argparse
import getpass
import sys
import sqlite3
import warnings
from pathlib import Path

from dotenv import load_dotenv

from src.paper.admin import provision_admin
from src.paper.accounts import AccountExistsError


def main(argv=None, *, role='admin'):
    class SecureParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'Invalid command options. Passwords are accepted only through hidden prompts.\n')
    parser = SecureParser(description=f'Create an independent {role} account using a hidden password prompt.')
    identities = parser.add_mutually_exclusive_group(required=role == 'user')
    if role == 'admin':
        identities.add_argument('--email', help='Admin email; prompted when neither identity option is supplied.')
    identities.add_argument('--username', help='Unique user ID (3–40 ASCII letters/digits/dots/underscores/hyphens).')
    if role == 'admin':
        parser.add_argument('--promote-existing', action='store_true', help='Explicitly promote an existing normal account, preserving its password and portfolios.')
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).resolve().parents[2] / '.env')
    if not sys.stdin.isatty():
        print('Use an interactive terminal; password input through pipes is disabled.', file=sys.stderr)
        return 1
    try:
        if args.username and getattr(args, 'promote_existing', False):
            raise ValueError('Username creation cannot promote existing accounts.')
        email = None if args.username else args.email or input('Admin email: ')
        if getattr(args, 'promote_existing', False):
            confirmation = input('Promote this existing account and preserve its password? Type PROMOTE: ')
            if confirmation != 'PROMOTE':
                print('Cancelled. No account changed.')
                return 1
            # No new password is collected or stored when promoting an existing account.
            result = provision_admin(email, None, promote_existing=True)
        else:
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                password = getpass.getpass('Password (8–128 characters): ')
                confirmed = getpass.getpass('Confirm password: ')
            if password != confirmed:
                print('Passwords do not match. No account changed.', file=sys.stderr)
                return 1
            if args.username:
                from src.paper.accounts import provision_username_account
                result = provision_username_account(args.username, password, role=role)
            else:
                result = provision_admin(email, password)
        print({'created':'Administrator created.' if role == 'admin' else 'User created.', 'already_exists':'Administrator already exists; password and account unchanged.', 'promoted_password_preserved':'Account promoted; existing password and portfolios preserved.'}[result])
        return 0
    except AccountExistsError:
        print('User ID already exists. No account changed.', file=sys.stderr)
        return 1
    except ValueError:
        print('Unable to create account: invalid or duplicate user ID, password requirements, or incompatible options. Existing accounts are preserved.', file=sys.stderr)
        return 1
    except (RuntimeError, sqlite3.Error, getpass.GetPassWarning):
        print('Unable to provision account. Check identity/password requirements and database configuration. Existing accounts are preserved.', file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled. No incomplete account was created.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
