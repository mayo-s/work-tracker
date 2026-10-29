"""Reset a forgotten password: python -m src.modules.auth set-password USERNAME_OR_EMAIL [--db PATH]."""

import argparse
import getpass
import sys
from collections.abc import Callable

from src.models.users import PASSWORD_MIN_LENGTH
from src.modules.storage.database import Database, database_path
from src.modules.storage.users import UserRepository


def main(argv: list[str] | None = None, read_password: Callable[[str], str] = getpass.getpass) -> int:
    parser = argparse.ArgumentParser(prog='python -m src.modules.auth', description='Reset the password of a user.')
    parser.add_argument('command', choices=['set-password'])
    parser.add_argument('login', help='username or e-mail address')
    parser.add_argument('--db', default=database_path(), help='database file (default: $WORK_TRACKER_DB or work_tracker.db)')
    args = parser.parse_args(argv)
    password = read_password('New password: ')
    if len(password) < PASSWORD_MIN_LENGTH or password != read_password('Repeat it: '):
        print(f'Not changed: the password needs at least {PASSWORD_MIN_LENGTH} characters, entered twice the same.',
              file=sys.stderr)
        return 1
    with Database(args.db).transaction() as conn:
        users = UserRepository(conn)
        user = users.by_login(args.login)
        if user is None:
            print(f'No user {args.login!r}', file=sys.stderr)
            return 1
        users.set_password(user.id, password)
    print(f'Password of {user.username} changed; all their sessions are ended.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
