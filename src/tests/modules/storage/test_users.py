import datetime as dt
import uuid

import pytest

from src.modules.storage.errors import ConflictError
from src.modules.storage.users import FailedLogins, SessionRepository, UserRepository
from src.tests.users import PASCAL, RAINER, USER

LOGIN = dt.datetime(2026, 10, 29, 8, 0)


@pytest.fixture
def users(conn):
    return UserRepository(conn)


def test_add_and_find_by_username_or_email_ignoring_case(users):
    added = users.add(RAINER, 'correct horse battery')
    assert users.count() == 2  # the test database's first user and Rainer
    assert users.by_login('RAINER') == added
    assert users.by_login(' Rainer.Zufall@Example.com ') == added
    assert users.by_login(PASCAL.username) is None


def test_ids_are_random_uuids(users):
    rainer, pascal = (users.add(person, 'correct horse battery').id for person in (RAINER, PASCAL))
    assert (uuid.UUID(rainer).version, uuid.UUID(pascal).version) == (4, 4)
    assert rainer != pascal


def test_first_user_is_the_first_created_not_the_smallest_id(conn):
    UserRepository(conn, new_id=lambda: '00000000-0000-4000-8000-000000000001').add(RAINER, 'correct horse battery')
    assert UserRepository(conn).first_id() == USER


@pytest.mark.parametrize('changes, field', [
    ({'username': 'RAINER'}, 'username'), ({'email': 'RAINER.ZUFALL@example.com'}, 'e-mail'),
])
def test_username_and_email_are_unique(users, changes, field):
    users.add(RAINER, 'correct horse battery')
    duplicate = RAINER.model_copy(update={'username': PASCAL.username, 'email': PASCAL.email} | changes)
    with pytest.raises(ConflictError, match=field):
        users.add(duplicate, 'correct horse battery')


def test_password(users, conn):
    user = users.add(RAINER, 'correct horse battery')
    assert users.check_password(user.id, 'correct horse battery')
    token = SessionRepository(conn).start(user.id, LOGIN)
    users.set_password(user.id, 'another long password')
    assert users.check_password(user.id, 'another long password')
    assert SessionRepository(conn).user_id(token, LOGIN) == (None, False)  # all sessions ended


def test_update_profile(users):
    user = users.add(RAINER, 'correct horse battery')
    changed = users.update(user.model_copy(update={'last_name': 'Schuetz', 'email': 'm@example.com'}))
    assert users.get(user.id) == changed


def test_session_lasts_24_hours_since_the_last_activity(users, conn):
    sessions = SessionRepository(conn)
    rainer = users.add(RAINER, 'correct horse battery').id
    token = sessions.start(rainer, LOGIN)
    assert sessions.user_id(token, LOGIN + dt.timedelta(minutes=20)) == (rainer, False)  # renewed at most every 30 minutes
    assert sessions.user_id(token, LOGIN + dt.timedelta(hours=23)) == (rainer, True)  # now valid until 23 h + 24 h
    assert sessions.user_id(token, LOGIN + dt.timedelta(hours=46)) == (rainer, True)
    assert sessions.user_id(token, LOGIN + dt.timedelta(hours=70, minutes=1)) == (None, False)


def test_unknown_and_ended_sessions(users, conn):
    sessions = SessionRepository(conn)
    token = sessions.start(users.add(RAINER, 'correct horse battery').id, LOGIN)
    assert sessions.user_id('unknown', LOGIN) == (None, False)
    sessions.end(token)
    assert sessions.user_id(token, LOGIN) == (None, False)


def test_tokens_are_stored_hashed(users, conn):
    token = SessionRepository(conn).start(users.add(RAINER, 'correct horse battery').id, LOGIN)
    stored = conn.execute('SELECT token_hash FROM sessions').fetchone()[0]
    assert token not in stored and len(stored) == 64


def test_failed_logins_pause_after_five_within_a_minute(conn):
    failed = FailedLogins(conn)
    for second in range(5):
        assert not failed.paused(LOGIN + dt.timedelta(seconds=second))
        failed.add(LOGIN + dt.timedelta(seconds=second))
    assert failed.paused(LOGIN + dt.timedelta(seconds=30))
    assert not failed.paused(LOGIN + dt.timedelta(seconds=61))
    failed.clear()
    assert not failed.paused(LOGIN + dt.timedelta(seconds=30))
