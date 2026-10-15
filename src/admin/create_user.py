"""Create a normal account with hidden, confirmed password input."""
from .create_admin import main as provision_cli


def main(argv=None):
    return provision_cli(argv, role='user')


if __name__ == '__main__':
    raise SystemExit(main())
