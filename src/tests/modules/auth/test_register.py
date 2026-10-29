import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.settings import set_registration

NOW = dt.datetime(2026, 10, 29, 8, 0)
PASCAL = {'username': 'pascal', 'email': 'turbo.pascal@example.com', 'first_name': 'Pascal', 'last_name': 'Turbo',
          'password': 'correct horse battery'}


@pytest.fixture
def app(database):
    return testing.TestClient(create_app(database, auth=True, clock=lambda: NOW))


@pytest.fixture
def registration(database):
    with database.transaction() as conn:
        set_registration(conn, True)


def register(app, **changes):
    return app.simulate_post('/api/auth/register', json=PASCAL | changes)


def test_off_by_default(app):
    assert (app.simulate_get('/register').status, register(app).status) == (falcon.HTTP_404, falcon.HTTP_404)
    assert app.simulate_get('/api/auth/status').json['registration'] is False


def test_not_with_the_login_off(database, registration):
    app = testing.TestClient(create_app(database, auth=False))
    assert (app.simulate_get('/register').status, register(app).status) == (falcon.HTTP_404, falcon.HTTP_404)


def test_page_is_open_while_on(app, registration):
    assert app.simulate_get('/register').status == falcon.HTTP_200


def test_new_user_is_logged_in_and_set_up_first(app, registration):
    result = register(app)
    assert (result.status, result.json['username'], result.json['role']) == (falcon.HTTP_201, 'pascal', 'user')
    cookies = {'wt_session': result.cookies['wt_session'].value}
    week = app.simulate_get('/week', cookies=cookies)
    assert (week.status, week.headers['location']) == (falcon.HTTP_303, '/setup')
    assert app.simulate_get('/api/admin/users', cookies=cookies).status == falcon.HTTP_403


def test_taken_username(app, registration):
    assert register(app, username='klara').status == falcon.HTTP_409


def test_registrations_and_failed_logins_pause_together(app, registration):
    for number in range(4):
        register(app, username=f'pascal{number}', email=f'pascal{number}@example.com')
    app.simulate_post('/api/auth/login', json={'login': 'klara', 'password': 'wrong password!'})
    assert register(app).status == falcon.HTTP_429
    assert app.simulate_post('/api/auth/login', json={'login': 'klara', 'password': 'wrong password!'}).status \
        == falcon.HTTP_429
