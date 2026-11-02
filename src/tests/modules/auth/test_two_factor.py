"""Two-factor login (SPEC 5.6, TASKS.md 9.1g1): set up in the account with a first code, then needed at every login;
each code works once."""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.lib.totp import code_at, time_step
from src.tests.users import PASSWORD


class Clock:
    def __init__(self):
        self.now = dt.datetime(2026, 11, 2, 9, 0)

    def __call__(self):
        return self.now

    def code(self, secret, steps_later=0):
        return code_at(secret, time_step(self.now) + steps_later)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def app(database, clock):
    return testing.TestClient(create_app(database, auth=True, clock=clock))


def login(app, code=None):
    return app.simulate_post('/api/auth/login', json={'login': 'klara', 'password': PASSWORD, 'code': code})


@pytest.fixture
def klara(app):
    return {'wt_session': login(app).cookies['wt_session'].value}


@pytest.fixture
def secret(app, klara, clock):
    """Klara set up two-factor login and confirmed it with a code."""
    setup = app.simulate_post('/api/auth/me/two-factor', cookies=klara).json
    app.simulate_put('/api/auth/me/two-factor', cookies=klara, json={'code': clock.code(setup['secret'])})
    clock.now += dt.timedelta(minutes=1)
    return setup['secret']


def test_the_setup_shows_the_secret_as_qr_code_and_text(app, klara):
    result = app.simulate_post('/api/auth/me/two-factor', cookies=klara)
    assert result.status == falcon.HTTP_201
    setup = result.json
    assert setup['uri'].startswith('otpauth://totp/Work%20Tracker%3Aklara?secret=' + setup['secret'])
    assert setup['qr'].startswith('data:image/svg+xml')
    assert app.simulate_get('/api/auth/me/two-factor', cookies=klara).json == {'enabled': False}  # not confirmed yet
    assert login(app).status == falcon.HTTP_200  # so the login needs no code yet


def test_a_first_code_confirms_it(app, klara, clock):
    setup = app.simulate_post('/api/auth/me/two-factor', cookies=klara).json
    wrong = app.simulate_put('/api/auth/me/two-factor', cookies=klara, json={'code': clock.code(setup['secret'], 5)})
    assert wrong.status == falcon.HTTP_403
    right = app.simulate_put('/api/auth/me/two-factor', cookies=klara, json={'code': clock.code(setup['secret'])})
    assert right.json == {'enabled': True}
    assert app.simulate_get('/api/auth/status', cookies=klara).json['user']['two_factor'] is True


def test_the_login_asks_for_the_code(app, secret):
    result = login(app)
    assert (result.status, result.json['code']) == (falcon.HTTP_401, 'two_factor_required')
    assert login(app, '000000' if code_at(secret, 0) != '000000' else '111111').status == falcon.HTTP_401


def test_the_login_with_the_code(app, secret, clock):
    assert login(app, clock.code(secret)).status == falcon.HTTP_200


def test_each_code_works_once(app, secret, clock):
    code = clock.code(secret)
    login(app, code)
    result = login(app, code)
    assert (result.status, result.json['description']) == (
        falcon.HTTP_401, 'The code is wrong; enter the current one of your authenticator app')


def test_wrong_codes_count_as_failed_logins(app, secret, clock):
    for _ in range(5):
        login(app, clock.code(secret, 10))
    assert login(app, clock.code(secret)).status == falcon.HTTP_429


def test_a_missing_code_is_no_failed_login(app, secret, clock):
    for _ in range(5):
        login(app)
    assert login(app, clock.code(secret)).status == falcon.HTTP_200


def test_switched_off_with_the_password(app, klara, secret):
    wrong = app.simulate_post('/api/auth/me/two-factor/off', cookies=klara, json={'password': 'not it'})
    assert wrong.status == falcon.HTTP_403
    assert app.simulate_post('/api/auth/me/two-factor/off', cookies=klara, json={'password': PASSWORD}).status == \
        falcon.HTTP_204
    assert login(app).status == falcon.HTTP_200


def test_no_second_setup_while_it_is_on(app, klara, secret):
    assert app.simulate_post('/api/auth/me/two-factor', cookies=klara).status == falcon.HTTP_409


def test_confirming_needs_a_setup(app, klara):
    result = app.simulate_put('/api/auth/me/two-factor', cookies=klara, json={'code': '123456'})
    assert (result.status, result.json['description']) == (falcon.HTTP_409, 'Start the setup first')
