"""Create independent admins with hidden terminal input, never password arguments."""
import argparse
import getpass
import sys
import warnings
from pathlib import Path

from dotenv import load_dotenv

from src.paper.admin import provision_admin


def main(argv=None):
    class SecureParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'Invalid command options. Passwords are accepted only through hidden prompts.\n')
    parser = SecureParser(description='Create an independent administrator using a hidden password prompt.')
    parser.add_argument('--email', help='Admin email; prompted when omitted.')
    parser.add_argument('--promote-existing', action='store_true', help='Explicitly promote an existing normal account, preserving its password and portfolios.')
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).resolve().parents[2] / '.env')
    if not sys.stdin.isatty():
        print('Use an interactive terminal; password input through pipes is disabled.', file=sys.stderr)
        return 1
    try:
        email = args.email or input('Admin email: ')
        if args.promote_existing:
            confirmation = input('Promote this existing account and preserve its password? Type PROMOTE: ')
            if confirmation != 'PROMOTE':
                print('Cancelled. No account changed.')
                return 1
            # No new password is collected or stored when promoting an existing account.
            result = provision_admin(email, None, promote_existing=True)
        else:
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                password = getpass.getpass('Admin password (14–128 characters): ')
                confirmed = getpass.getpass('Confirm password: ')
            if password != confirmed:
                print('Passwords do not match. No account changed.', file=sys.stderr)
                return 1
            result = provision_admin(email, password)
        print({'created':'Administrator created.', 'already_exists':'Administrator already exists; password and account unchanged.', 'promoted_password_preserved':'Account promoted; existing password and portfolios preserved.'}[result])
        return 0
    except (RuntimeError, ValueError, getpass.GetPassWarning):
        print('Unable to provision administrator. Check the email/password requirements, database configuration, and explicit promotion option. Existing accounts are preserved.', file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled. No incomplete account was created.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
