import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.database import Database
from src.modules.auth.__main__ import main
from src.modules.storage.owners import NO_OWNER

RAINER = {'username': 'rainer', 'email': 'rainer.zufall@example.com', 'first_name': 'Rainer', 'last_name': 'Zufall',
          'password': 'correct horse battery'}


class Clock:
    def __init__(self):
        self.now = dt.datetime(2026, 10, 29, 8, 0)

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


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


def session(result):
    return {'wt_session': result.cookies['wt_session'].value}


@pytest.fixture
def cookies(app):
    """Rainer, logged in."""
    return session(app.simulate_post('/api/auth/first-user', json=RAINER))


def login(app, name='rainer', password='correct horse battery'):
    return app.simulate_post('/api/auth/login', json={'login': name, 'password': password})


def test_without_a_user_pages_forward_to_login_to_create_it(app):
    result = app.simulate_get('/year', query_string='year=2025')
    assert (result.status, result.headers['location']) == (falcon.HTTP_303, '/login?next=%2Fyear%3Fyear%3D2025')
    assert app.simulate_get('/api/auth/status').json == {'enabled': True, 'has_users': False, 'user': None}


def test_first_user_logs_in_and_only_once(app):
    result = app.simulate_post('/api/auth/first-user', json=RAINER)
    assert (result.status, result.json['username']) == (falcon.HTTP_201, 'rainer')
    assert app.simulate_get('/api/auth/me', cookies=session(result)).json['email'] == 'rainer.zufall@example.com'
    assert app.simulate_post('/api/auth/first-user', json=RAINER | {'username': 'pascal'}).status == falcon.HTTP_409


@pytest.mark.parametrize('path', ['/', '/week', '/settings'])
def test_pages_forward_to_login(app, cookies, path):
    result = app.simulate_get(path)
    assert (result.status, result.headers['location']) == (falcon.HTTP_303, f'/login?next={path.replace("/", "%2F")}')
    assert app.simulate_get(path, cookies=cookies).status == falcon.HTTP_200


@pytest.mark.parametrize('path', ['/api/dashboard', '/api/settings', '/api/auth/me'])
def test_api_answers_401(app, cookies, path):
    assert app.simulate_get(path).status == falcon.HTTP_401
    assert app.simulate_get(path, cookies=cookies).status == falcon.HTTP_200


@pytest.mark.parametrize('path', ['/login', '/health', '/apidoc/openapi.json', '/static/css/main.css', '/api/auth/status'])
def test_open_paths(app, cookies, path):
    assert app.simulate_get(path).status == falcon.HTTP_200


@pytest.mark.parametrize('name', ['rainer', 'RAINER', 'rainer.zufall@example.com', 'Rainer.Zufall@Example.COM'])
def test_login_with_username_or_email(app, cookies, name):
    result = login(app, name)
    assert (result.status, result.json['first_name']) == (falcon.HTTP_200, 'Rainer')
    assert app.simulate_get('/api/dashboard', cookies=session(result)).status == falcon.HTTP_200


def test_session_cookie(app, cookies):
    cookie = login(app).cookies['wt_session']
    assert (cookie.http_only, cookie.same_site, cookie.path, cookie.max_age) == (True, 'Strict', '/', 86400)


@pytest.mark.parametrize('name, password', [('rainer', 'wrong password!'), ('pascal', 'correct horse battery')])
def test_wrong_login(app, cookies, name, password):
    result = login(app, name, password)
    assert (result.status, result.json['description']) == (falcon.HTTP_401, 'Wrong username, e-mail address or password')


def test_logins_pause_after_five_failures(app, cookies, clock):
    for _ in range(5):
        login(app, password='wrong password!')
    assert login(app).status == falcon.HTTP_429
    clock.now += dt.timedelta(minutes=1, seconds=1)
    assert login(app).status == falcon.HTTP_200


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


@pytest.mark.parametrize('body', [
    {'username': 'm', 'email': 'rainer.zufall@example.com', 'first_name': 'Rainer'},
    {'username': 'rainer', 'email': 'rainer', 'first_name': 'Rainer'},
    {'username': 'rainer', 'email': 'rainer.zufall@example.com', 'first_name': ''},
])
def test_profile_rejects_invalid_values(app, cookies, body):
    assert app.simulate_put('/api/auth/me', cookies=cookies, json=body).status_code == 422


def test_password_change_ends_other_sessions_and_keeps_this_one(app, cookies):
    other = session(login(app))
    result = app.simulate_put('/api/auth/me/password', cookies=cookies,
                              json={'current_password': 'correct horse battery', 'new_password': 'another long password'})
    assert result.status == falcon.HTTP_204
    assert app.simulate_get('/api/dashboard', cookies=other).status == falcon.HTTP_401
    assert app.simulate_get('/api/dashboard', cookies=session(result)).status == falcon.HTTP_200
    assert login(app, password='another long password').status == falcon.HTTP_200


@pytest.mark.parametrize('body, status', [
    ({'current_password': 'wrong password!', 'new_password': 'another long password'}, 403),
    ({'current_password': 'correct horse battery', 'new_password': 'too short'}, 422),
])
def test_password_change_errors(app, cookies, body, status):
    assert app.simulate_put('/api/auth/me/password', cookies=cookies, json=body).status_code == status


def test_login_off_leaves_everything_open(unclaimed):
    app = testing.TestClient(create_app(unclaimed, auth=False))
    assert app.simulate_get('/api/dashboard').status == falcon.HTTP_200
    assert app.simulate_get('/api/auth/status').json == {'enabled': False, 'has_users': False, 'user': None}


def test_command_resets_a_forgotten_password(app, cookies, unclaimed):
    answers = iter(['a new long password', 'a new long password'])
    assert main(['set-password', 'rainer.zufall@example.com', '--db', str(unclaimed.path)], lambda prompt: next(answers)) == 0
    assert login(app, password='a new long password').status == falcon.HTTP_200
    assert app.simulate_get('/api/dashboard', cookies=cookies).status == falcon.HTTP_401


@pytest.mark.parametrize('answers', [['short', 'short'], ['a new long password', 'another long password']])
def test_command_refuses_short_or_different_passwords(database, answers):
    replies = iter(answers)
    assert main(['set-password', 'rainer', '--db', str(database.path)], lambda prompt: next(replies)) == 1
