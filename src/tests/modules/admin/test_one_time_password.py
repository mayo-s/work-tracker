"""One-time passwords (SPEC 5.6): the admin sets one for a user who forgot theirs, who chooses their own at the next
login before anything else. The whole app runs on SQLite and on DynamoDB (moto)."""

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.lib.passwords import one_time_password
from src.models.users import password_problem
from src.tests.helpers import logged_in, login, session
from src.tests.ids import UNKNOWN
from src.tests.users import HANS, KLARA, PASSWORD

NEW = 'my own password 7!'


@pytest.fixture
def hans_id(storage):
    with storage.transaction() as store:
        store.users().add(KLARA, PASSWORD)  # an admin
        return store.users().add(HANS, PASSWORD).id


@pytest.fixture
def app(storage, hans_id):
    return testing.TestClient(create_app(storage=storage, auth=True))


def give_one_time_password(app, hans_id):
    result = app.simulate_post(f'/api/admin/users/{hans_id}/one-time-password', cookies=logged_in(app, 'klara'))
    assert result.status == falcon.HTTP_201
    return result.json['password']


def test_one_time_passwords_meet_the_rules_and_differ():
    passwords = {one_time_password() for _ in range(50)}
    assert len(passwords) == 50 and all(password_problem(password) is None for password in passwords)


def test_the_old_password_and_sessions_end(app, hans_id):
    cookies = logged_in(app, 'hans')
    password = give_one_time_password(app, hans_id)
    assert app.simulate_get('/api/auth/me', cookies=cookies).status == falcon.HTTP_401
    assert login(app, 'hans').status == falcon.HTTP_401
    assert login(app, 'hans', password).status == falcon.HTTP_200


def test_until_the_new_password_only_the_password_page_works(app, hans_id):
    cookies = logged_in(app, 'hans', give_one_time_password(app, hans_id))
    assert app.simulate_get('/api/auth/status', cookies=cookies).json['user']['must_change_password'] is True
    week = app.simulate_get('/week', cookies=cookies)
    assert (week.status, week.headers['location']) == (falcon.HTTP_303, '/password')
    assert app.simulate_get('/api/days', query_string='week=2026-W44', cookies=cookies).status == falcon.HTTP_403
    assert app.simulate_get('/password', cookies=cookies).status == falcon.HTTP_200


def test_choosing_the_own_password_opens_everything_again(app, hans_id):
    password = give_one_time_password(app, hans_id)
    cookies = logged_in(app, 'hans', password)
    changed = app.simulate_put('/api/auth/me/password', cookies=cookies,
                               json={'current_password': password, 'new_password': NEW})
    assert changed.status == falcon.HTTP_204
    cookies = session(changed)
    assert app.simulate_get('/api/days', query_string='week=2026-W44', cookies=cookies).status == falcon.HTTP_200
    assert login(app, 'hans', password).status == falcon.HTTP_401  # one time only
    assert login(app, 'hans', NEW).status == falcon.HTTP_200


def test_the_admin_sees_who_has_not_chosen_yet(app, hans_id):
    give_one_time_password(app, hans_id)
    users = app.simulate_get('/api/admin/users', cookies=logged_in(app, 'klara')).json
    assert [(user['username'], user['must_change_password']) for user in users] == [('klara', False), ('hans', True)]


@pytest.mark.parametrize('viewer, user, status', [
    ('hans', 'klara', falcon.HTTP_403),  # only admins
    ('klara', 'klara', falcon.HTTP_409),  # not for the own account
    ('klara', UNKNOWN, falcon.HTTP_404),
])
def test_refused(app, storage, viewer, user, status):
    with storage.transaction() as store:
        ids = {account.username: account.id for account in store.users().all()}
    result = app.simulate_post(f'/api/admin/users/{ids.get(user, user)}/one-time-password', cookies=logged_in(app, viewer))
    assert result.status == status
