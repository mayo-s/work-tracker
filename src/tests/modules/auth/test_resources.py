import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.database import Database
from src.modules.auth.__main__ import main
from src.modules.storage.owners import NO_OWNER
from src.tests.helpers import Clock, login, session
from src.tests.users import PASSWORD

RAINER = {'username': 'rainer', 'email': 'rainer.zufall@example.com', 'first_name': 'Rainer', 'last_name': 'Zufall',
          'password': PASSWORD}
PASCAL = {'username': 'pascal', 'email': 'turbo.pascal@example.com', 'first_name': 'Pascal', 'last_name': 'Turbo',
          'password': 'a long root password 7?'}


@pytest.fixture
def clock():
    return Clock(dt.datetime(2026, 10, 29, 8, 0))


@pytest.fixture
def unclaimed(tmp_path):
    """A database in use (set up) but without a user yet, like one from before the login."""
    db = Database(tmp_path / 'unclaimed.db')
    db.migrate()
    with db.transaction() as conn:
        conn.execute("UPDATE user_settings SET value = '1' WHERE user_id = ? AND key = 'setup_done'", (NO_OWNER,))
    return db


@pytest.fixture
def app(unclaimed, clock):
    """That database with the login on."""
    return testing.TestClient(create_app(unclaimed, auth=True, clock=clock))


@pytest.fixture
def root(app):
    """Pascal, root, logged in."""
    return session(app.simulate_post('/api/auth/root', json=PASCAL))


@pytest.fixture
def cookies(app, root):
    """Rainer, logged in: he registered once root had opened the registration, and took over the records."""
    app.simulate_put('/api/admin/settings', cookies=root, json={'registration': True})
    return session(app.simulate_post('/api/auth/register', json=RAINER))


def test_without_a_user_pages_forward_to_login_to_create_it(app):
    result = app.simulate_get('/year', query_string='year=2025')
    assert (result.status, result.headers['location']) == (falcon.HTTP_303, '/login?next=%2Fyear%3Fyear%3D2025')
    status = {'enabled': True, 'has_users': False, 'has_root': False, 'user': None, 'registration': False,
              'team': None, 'invitations': 0, 'auditor': False, 'new_messages': 0, 'setup_token': False,
              'root_reset': False}
    assert app.simulate_get('/api/auth/status').json == status


def test_root_is_created_once_and_logs_in(app):
    result = app.simulate_post('/api/auth/root', json=PASCAL)
    assert (result.status, result.json['role']) == (falcon.HTTP_201, 'root')
    assert app.simulate_get('/api/auth/me', cookies=session(result)).json['email'] == 'turbo.pascal@example.com'
    again = app.simulate_post('/api/auth/root', json=RAINER)
    assert (again.status, again.json['description']) == (falcon.HTTP_409, 'There is a root already; log in instead')


# What root gets: its own pages and their API; the tracking pages forward to /admin, the tracking API is refused
ROOT_ACCESS = {'/admin': 200, '/settings': 200, '/api/admin/users': 200, '/api/theme': 200, '/imprint': 200,
               '/': 303, '/setup': 303, '/api/days': 403, '/api/settings': 403}


def test_root_runs_the_app_and_tracks_no_work(app, root):
    actual = {path: app.simulate_get(path, cookies=root).status_code for path in ROOT_ACCESS}
    assert actual == ROOT_ACCESS
    assert app.simulate_get('/week', cookies=root).headers['location'] == '/admin'
    assert app.simulate_get('/api/days', cookies=root).json['description'] == 'Root runs the app and tracks no work'


# What a visitor gets who is not logged in: the open paths; pages forward to the login, the API answers 401
VISITOR_ACCESS = {'/login': 200, '/health': 200, '/static/css/main.css': 200, '/api/auth/status': 200,
                  '/imprint': 200, '/settings': 303, '/api/dashboard': 401}


def test_pages_and_api_need_the_login(app, cookies):
    actual = {path: app.simulate_get(path).status_code for path in VISITOR_ACCESS}
    assert actual == VISITOR_ACCESS
    assert app.simulate_get('/settings').headers['location'] == '/login?next=%2Fsettings'
    logged_in = {path: app.simulate_get(path, cookies=cookies).status_code for path in ('/settings', '/api/dashboard')}
    assert logged_in == {'/settings': 200, '/api/dashboard': 200}


def test_login_with_the_email_address_too(app, cookies):
    result = login(app, 'Rainer.Zufall@Example.COM')
    assert (result.status, result.json['first_name']) == (falcon.HTTP_200, 'Rainer')
    assert app.simulate_get('/api/dashboard', cookies=session(result)).status == falcon.HTTP_200


def test_session_cookie(app, cookies):
    cookie = login(app, 'rainer').cookies['wt_session']
    assert (cookie.http_only, cookie.same_site, cookie.path, cookie.max_age) == (True, 'Strict', '/', 86400)


@pytest.mark.parametrize('name, password', [('rainer', 'wrong password!'), ('nobody', PASSWORD)])
def test_wrong_login(app, cookies, name, password):
    result = login(app, name, password)
    assert (result.status, result.json['description']) == (falcon.HTTP_401, 'Wrong username, e-mail address or password')


def test_logins_pause_after_five_failures(app, cookies, clock):
    for _ in range(5):
        login(app, 'rainer', 'wrong password!')
    assert login(app, 'rainer').status == falcon.HTTP_429
    clock.now += dt.timedelta(minutes=1, seconds=1)
    assert login(app, 'rainer').status == falcon.HTTP_200


def test_session_slides_with_activity_and_ends_after_24_hours_without(app, cookies, clock):
    clock.now += dt.timedelta(hours=23)
    renewed = app.simulate_get('/api/dashboard', cookies=cookies)
    assert renewed.status == falcon.HTTP_200
    assert renewed.cookies['wt_session'].max_age == 86400  # the cookie slides along
    clock.now += dt.timedelta(hours=23)
    assert app.simulate_get('/api/dashboard', cookies=cookies).status == falcon.HTTP_200
    clock.now += dt.timedelta(hours=24, minutes=1)
    assert app.simulate_get('/api/dashboard', cookies=cookies).status == falcon.HTTP_401


def test_logout(app, cookies):
    result = app.simulate_post('/api/auth/logout', cookies=cookies)
    assert result.status == falcon.HTTP_204
    assert result.cookies['wt_session'].value == ''
    assert app.simulate_get('/api/dashboard', cookies=cookies).status == falcon.HTTP_401


def test_profile(app, cookies):
    profile = {'username': 'rainer.z', 'email': 'rainer.zufall@example.org', 'first_name': 'Rainer', 'last_name': 'Z.'}
    changed = app.simulate_put('/api/auth/me', cookies=cookies, json=profile)
    assert (changed.status, changed.json['last_name']) == (falcon.HTTP_200, 'Z.')
    assert login(app, 'rainer.z').status == falcon.HTTP_200


def test_profile_rejects_invalid_values(app, cookies):
    body = {'username': 'rainer', 'email': 'rainer', 'first_name': 'Rainer'}
    assert app.simulate_put('/api/auth/me', cookies=cookies, json=body).status_code == 422


def test_password_change_ends_other_sessions_and_keeps_this_one(app, cookies):
    other = session(login(app, 'rainer'))
    result = app.simulate_put('/api/auth/me/password', cookies=cookies,
                              json={'current_password': PASSWORD,
                                    'new_password': 'another long password 2#'})
    assert result.status == falcon.HTTP_204
    assert app.simulate_get('/api/dashboard', cookies=other).status == falcon.HTTP_401
    assert app.simulate_get('/api/dashboard', cookies=session(result)).status == falcon.HTTP_200
    assert login(app, 'rainer', 'another long password 2#').status == falcon.HTTP_200
    log = app.simulate_get('/api/auth/me/audit', cookies=session(result)).json
    assert [(entry['action'], entry['detail']) for entry in log] == [('password_changed', '')]


@pytest.mark.parametrize('body, status', [
    ({'current_password': 'wrong password!', 'new_password': 'another long password 2#'}, 403),
    ({'current_password': PASSWORD, 'new_password': 'no digits or specials'}, 422),
])
def test_password_change_errors(app, cookies, body, status):
    assert app.simulate_put('/api/auth/me/password', cookies=cookies, json=body).status_code == status


def test_login_off_leaves_everything_open(unclaimed):
    app = testing.TestClient(create_app(unclaimed, auth=False))
    assert app.simulate_get('/api/dashboard').status == falcon.HTTP_200
    status = {'enabled': False, 'has_users': False, 'has_root': False, 'user': None, 'registration': False,
              'team': None, 'invitations': 0, 'auditor': False, 'new_messages': 0, 'setup_token': False,
              'root_reset': False}
    assert app.simulate_get('/api/auth/status').json == status


def test_command_resets_a_forgotten_password(app, cookies, unclaimed):
    answers = iter(['a new long password 3$', 'a new long password 3$'])
    assert main(['set-password', 'rainer.zufall@example.com', '--db', str(unclaimed.path)], lambda prompt: next(answers)) == 0
    result = login(app, 'rainer', 'a new long password 3$')
    assert result.status == falcon.HTTP_200
    assert app.simulate_get('/api/dashboard', cookies=cookies).status == falcon.HTTP_401
    log = app.simulate_get('/api/auth/me/audit', cookies=session(result)).json
    assert [(entry['action'], entry['detail']) for entry in log] == [('password_changed', 'command')]


@pytest.mark.parametrize('answers', [
    ['no digits or specials', 'no digits or specials'], ['a new long password 3$', 'another long password 2#'],
])
def test_command_refuses_weak_or_different_passwords(database, answers):
    replies = iter(answers)
    assert main(['set-password', 'rainer', '--db', str(database.path)], lambda prompt: next(replies)) == 1


def test_weak_passwords_are_refused_with_the_rule(app):
    result = app.simulate_post('/api/auth/root', json=PASCAL | {'password': 'only letters here'})
    assert result.status_code == 422
    assert 'letters, digits and a special character' in result.json[0]['msg']
