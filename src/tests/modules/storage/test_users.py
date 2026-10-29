import datetime as dt
import uuid

import pytest

from src.modules.storage.errors import ConflictError
from src.modules.storage.users import LoginAttempts, SessionRepository, UserRepository
from src.tests.users import PASCAL, RAINER, USER

LOGIN = dt.datetime(2026, 10, 29, 8, 0)


@pytest.fixture
def users(conn):
    return UserRepository(conn)


def test_add_and_find_by_username_or_email_ignoring_case(users):
    added = users.add(RAINER, 'correct horse battery 9!')
    assert users.count() == 2  # the test database's first user and Rainer
    assert users.by_login('RAINER') == added
    assert users.by_login(' Rainer.Zufall@Example.com ') == added
    assert users.by_login(PASCAL.username) is None


def test_ids_are_random_uuids(users):
    rainer, pascal = (users.add(person, 'correct horse battery 9!').id for person in (RAINER, PASCAL))
    assert (uuid.UUID(rainer).version, uuid.UUID(pascal).version) == (4, 4)
    assert rainer != pascal


def test_first_user_is_the_first_created_not_the_smallest_id(conn):
    UserRepository(conn, new_id=lambda: '00000000-0000-4000-8000-000000000001').add(RAINER, 'correct horse battery 9!')
    assert UserRepository(conn).first_id() == USER


@pytest.mark.parametrize('changes, field', [
    ({'username': 'RAINER'}, 'username'), ({'email': 'RAINER.ZUFALL@example.com'}, 'e-mail'),
])
def test_username_and_email_are_unique(users, changes, field):
    users.add(RAINER, 'correct horse battery 9!')
    duplicate = RAINER.model_copy(update={'username': PASCAL.username, 'email': PASCAL.email} | changes)
    with pytest.raises(ConflictError, match=field):
        users.add(duplicate, 'correct horse battery 9!')


def test_password(users, conn):
    user = users.add(RAINER, 'correct horse battery 9!')
    assert users.check_password(user.id, 'correct horse battery 9!')
    token = SessionRepository(conn).start(user.id, LOGIN)
    users.set_password(user.id, 'another long password 2#')
    assert users.check_password(user.id, 'another long password 2#')
    assert SessionRepository(conn).user_id(token, LOGIN) == (None, False)  # all sessions ended


def test_update_profile(users):
    user = users.add(RAINER, 'correct horse battery 9!')
    changed = users.update(user.model_copy(update={'last_name': 'Schuetz', 'email': 'm@example.com'}))
    assert users.get(user.id) == changed


def test_session_lasts_24_hours_since_the_last_activity(users, conn):
    sessions = SessionRepository(conn)
    rainer = users.add(RAINER, 'correct horse battery 9!').id
    token = sessions.start(rainer, LOGIN)
    assert sessions.user_id(token, LOGIN + dt.timedelta(minutes=20)) == (rainer, False)  # renewed at most every 30 minutes
    assert sessions.user_id(token, LOGIN + dt.timedelta(hours=23)) == (rainer, True)  # now valid until 23 h + 24 h
    assert sessions.user_id(token, LOGIN + dt.timedelta(hours=46)) == (rainer, True)
    assert sessions.user_id(token, LOGIN + dt.timedelta(hours=70, minutes=1)) == (None, False)


def test_unknown_and_ended_sessions(users, conn):
    sessions = SessionRepository(conn)
    token = sessions.start(users.add(RAINER, 'correct horse battery 9!').id, LOGIN)
    assert sessions.user_id('unknown', LOGIN) == (None, False)
    sessions.end(token)
    assert sessions.user_id(token, LOGIN) == (None, False)


def test_tokens_are_stored_hashed(users, conn):
    token = SessionRepository(conn).start(users.add(RAINER, 'correct horse battery 9!').id, LOGIN)
    stored = conn.execute('SELECT token_hash FROM sessions').fetchone()[0]
    assert token not in stored and len(stored) == 64


def test_failed_logins_pause_after_five_within_a_minute(conn):
    attempts = LoginAttempts(conn)
    for second in range(5):
        assert not attempts.paused(LOGIN + dt.timedelta(seconds=second))
        attempts.add(LOGIN + dt.timedelta(seconds=second))
    assert attempts.paused(LOGIN + dt.timedelta(seconds=30))
    assert not attempts.paused(LOGIN + dt.timedelta(seconds=61))
    attempts.clear_failed()
    assert not attempts.paused(LOGIN + dt.timedelta(seconds=30))


def test_registrations_count_towards_the_pause_and_stay_after_a_login(conn):
    attempts = LoginAttempts(conn)
    for second in range(4):
        attempts.add(LOGIN + dt.timedelta(seconds=second), 'registration')
    attempts.add(LOGIN + dt.timedelta(seconds=4))
    assert attempts.paused(LOGIN + dt.timedelta(seconds=5))
    attempts.clear_failed()
    assert not attempts.paused(LOGIN + dt.timedelta(seconds=5))
    attempts.add(LOGIN + dt.timedelta(seconds=6), 'registration')
    assert attempts.paused(LOGIN + dt.timedelta(seconds=7))


def test_a_user_records_registration_and_last_login(conn):
    users = UserRepository(conn, clock=lambda: LOGIN)
    rainer = users.add(RAINER, 'correct horse battery 9!')
    assert (rainer.registered_at, rainer.last_login_at, rainer.active) == (LOGIN, None, True)
    SessionRepository(conn).start(rainer.id, LOGIN + dt.timedelta(hours=2))
    assert users.get(rainer.id).last_login_at == LOGIN + dt.timedelta(hours=2)


def test_all_users_in_the_order_they_registered(users):
    users.add(RAINER, 'correct horse battery 9!')
    users.add(PASCAL, 'correct horse battery 9!')
    assert [user.username for user in users.all()] == ['klara', 'rainer', 'pascal']


def test_change_role(users):
    rainer = users.add(RAINER, 'correct horse battery 9!')
    assert users.set_role(rainer.id, 'admin').role == 'admin'


def test_deactivating_ends_the_sessions_and_keeps_the_user(users, conn):
    sessions = SessionRepository(conn)
    rainer = users.add(RAINER, 'correct horse battery 9!')
    token = sessions.start(rainer.id, LOGIN)
    assert users.set_active(rainer.id, False).active is False
    assert sessions.user_id(token, LOGIN) == (None, False)
    assert users.set_active(rainer.id, True).active is True
    assert sessions.user_id(sessions.start(rainer.id, LOGIN), LOGIN) == (rainer.id, False)
