"""SQLite only: what the shared behaviour (test_contract_users.py) cannot see from outside."""

import datetime as dt

from src.modules.storage.users import SessionRepository, UserRepository
from src.tests.users import RAINER, USER

LOGIN = dt.datetime(2026, 10, 29, 8, 0)


def test_first_user_is_the_first_created_not_the_smallest_id(conn):
    UserRepository(conn, new_id=lambda: '00000000-0000-4000-8000-000000000001').add(RAINER, 'correct horse battery 9!')
    assert UserRepository(conn).first_id() == USER


def test_tokens_are_stored_hashed(conn):
    token = SessionRepository(conn).start(UserRepository(conn).add(RAINER, 'correct horse battery 9!').id, LOGIN)
    stored = conn.execute('SELECT token_hash FROM sessions').fetchone()[0]
    assert token not in stored and len(stored) == 64
