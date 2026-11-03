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
    assert app.simulate_get('/api/auth/me/two-factor', cookies=klara).json['enabled'] is False  # not confirmed yet
    assert login(app).status == falcon.HTTP_200  # so the login needs no code yet


def test_a_first_code_confirms_it(app, klara, clock):
    setup = app.simulate_post('/api/auth/me/two-factor', cookies=klara).json
    wrong = app.simulate_put('/api/auth/me/two-factor', cookies=klara, json={'code': clock.code(setup['secret'], 5)})
    assert wrong.status == falcon.HTTP_403
    right = app.simulate_put('/api/auth/me/two-factor', cookies=klara, json={'code': clock.code(setup['secret'])})
    assert len(set(right.json['recovery_codes'])) == 10
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
        falcon.HTTP_401, 'The code is wrong; enter the current one of your authenticator app, or a recovery code')


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


def test_recovery_codes_work_once_each_in_place_of_a_code(app, klara, clock):
    setup = app.simulate_post('/api/auth/me/two-factor', cookies=klara).json
    codes = app.simulate_put('/api/auth/me/two-factor', cookies=klara, json={'code': clock.code(setup['secret'])}).json
    first = codes['recovery_codes'][0]
    assert login(app, first.upper().replace('-', ' ')).status == falcon.HTTP_200  # case, dashes and spaces do not matter
    assert login(app, first).status == falcon.HTTP_401
    assert app.simulate_get('/api/auth/me/two-factor', cookies=klara).json['recovery_left'] == 9


def test_new_recovery_codes_replace_the_old_ones(app, klara, clock):
    setup = app.simulate_post('/api/auth/me/two-factor', cookies=klara).json
    old = app.simulate_put('/api/auth/me/two-factor', cookies=klara, json={'code': clock.code(setup['secret'])}).json
    assert app.simulate_post('/api/auth/me/two-factor/recovery', cookies=klara, json={'password': 'not it'}).status == \
        falcon.HTTP_403
    new = app.simulate_post('/api/auth/me/two-factor/recovery', cookies=klara, json={'password': PASSWORD})
    assert new.status == falcon.HTTP_201
    assert login(app, old['recovery_codes'][0]).status == falcon.HTTP_401
    assert login(app, new.json['recovery_codes'][0]).status == falcon.HTTP_200


def login_remembering(app, code):
    return app.simulate_post('/api/auth/login', json={'login': 'klara', 'password': PASSWORD, 'code': code, 'remember': True})


def test_a_remembered_browser_needs_no_code_for_30_days(app, secret, clock):
    first = login_remembering(app, clock.code(secret))
    browser = first.cookies['wt_browser']
    assert (browser.http_only, browser.same_site, browser.max_age) == (True, 'Strict', 30 * 24 * 3600)
    again = app.simulate_post('/api/auth/login', cookies={'wt_browser': browser.value},
                              json={'login': 'klara', 'password': PASSWORD})
    assert again.status == falcon.HTTP_200
    clock.now += dt.timedelta(days=31)
    later = app.simulate_post('/api/auth/login', cookies={'wt_browser': browser.value},
                              json={'login': 'klara', 'password': PASSWORD})
    assert later.json['code'] == 'two_factor_required'


def test_a_new_password_forgets_the_browser(app, klara, secret, clock):
    browser = login_remembering(app, clock.code(secret)).cookies['wt_browser'].value
    session = {'wt_session': login(app, clock.code(secret, 1)).cookies['wt_session'].value}
    app.simulate_put('/api/auth/me/password', cookies=session,
                     json={'current_password': PASSWORD, 'new_password': 'another long password 2#'})
    again = app.simulate_post('/api/auth/login', cookies={'wt_browser': browser},
                              json={'login': 'klara', 'password': 'another long password 2#'})
    assert again.json['code'] == 'two_factor_required'


def test_without_remember_no_browser_is_remembered(app, secret, clock):
    assert 'wt_browser' not in login(app, clock.code(secret)).cookies


def new_app(app, cookies, code, password=PASSWORD):
    return app.simulate_post('/api/auth/me/two-factor/new-app', cookies=cookies, json={'password': password, 'code': code})


def test_a_new_app_replaces_the_old_one_once_a_code_of_it_confirms_it(app, klara, secret, clock):
    started = new_app(app, klara, clock.code(secret))
    assert started.status == falcon.HTTP_201
    fresh = started.json['secret']
    assert started.json['uri'].startswith('otpauth://totp/Work%20Tracker%3Aklara?secret=' + fresh)
    assert login(app, clock.code(secret, 1)).status == falcon.HTTP_200  # the old app works until confirmed
    confirmed = app.simulate_put('/api/auth/me/two-factor/new-app', cookies=klara, json={'code': clock.code(fresh)})
    assert confirmed.status == falcon.HTTP_204
    clock.now += dt.timedelta(minutes=1)
    assert login(app, clock.code(secret)).status == falcon.HTTP_401
    assert login(app, clock.code(fresh)).status == falcon.HTTP_200


def test_a_new_app_needs_the_password(app, klara, secret, clock):
    result = new_app(app, klara, clock.code(secret), password='not it')
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'The current password is wrong')


def test_a_new_app_needs_a_current_code(app, klara, secret, clock):
    result = new_app(app, klara, clock.code(secret, 10))
    assert (result.status, result.json['description']) == (
        falcon.HTTP_403, 'The code is wrong; enter the current one of your authenticator app, or a recovery code')


def test_a_recovery_code_starts_a_new_app(app, klara, clock):
    setup = app.simulate_post('/api/auth/me/two-factor', cookies=klara).json
    codes = app.simulate_put('/api/auth/me/two-factor', cookies=klara, json={'code': clock.code(setup['secret'])}).json
    assert new_app(app, klara, codes['recovery_codes'][0]).status == falcon.HTTP_201
    assert app.simulate_get('/api/auth/me/two-factor', cookies=klara).json['recovery_left'] == 9


def test_wrong_codes_for_a_new_app_count_as_failed_logins(app, klara, secret, clock):
    for _ in range(5):
        new_app(app, klara, clock.code(secret, 10))
    assert new_app(app, klara, clock.code(secret)).status == falcon.HTTP_429


def test_a_wrong_code_of_the_new_app_keeps_the_old_one(app, klara, secret, clock):
    fresh = new_app(app, klara, clock.code(secret)).json['secret']
    wrong = app.simulate_put('/api/auth/me/two-factor/new-app', cookies=klara, json={'code': clock.code(fresh, 5)})
    assert wrong.status == falcon.HTTP_403
    assert login(app, clock.code(secret, 1)).status == falcon.HTTP_200


def test_the_recovery_codes_stay_with_a_new_app(app, klara, clock):
    setup = app.simulate_post('/api/auth/me/two-factor', cookies=klara).json
    codes = app.simulate_put('/api/auth/me/two-factor', cookies=klara, json={'code': clock.code(setup['secret'])}).json
    clock.now += dt.timedelta(minutes=1)
    fresh = new_app(app, klara, clock.code(setup['secret'])).json['secret']
    app.simulate_put('/api/auth/me/two-factor/new-app', cookies=klara, json={'code': clock.code(fresh)})
    assert login(app, codes['recovery_codes'][0]).status == falcon.HTTP_200


def test_confirming_needs_a_new_app_started(app, klara, secret, clock):
    result = app.simulate_put('/api/auth/me/two-factor/new-app', cookies=klara, json={'code': clock.code(secret)})
    assert (result.status, result.json['description']) == (falcon.HTTP_409, 'Start with the password and a current code first')


def test_no_new_app_while_two_factor_login_is_off(app, klara):
    result = new_app(app, klara, '123456')
    assert (result.status, result.json['description']) == (falcon.HTTP_409, 'Two-factor login is off')


def own_log(app, cookies):
    return [entry['action'] for entry in app.simulate_get('/api/auth/me/audit', cookies=cookies).json]


def test_changes_to_two_factor_login_are_in_the_own_log(app, klara, secret, clock):
    fresh = new_app(app, klara, clock.code(secret)).json['secret']
    app.simulate_put('/api/auth/me/two-factor/new-app', cookies=klara, json={'code': clock.code(fresh)})
    app.simulate_post('/api/auth/me/two-factor/recovery', cookies=klara, json={'password': PASSWORD})
    app.simulate_post('/api/auth/me/two-factor/off', cookies=klara, json={'password': PASSWORD})
    assert own_log(app, klara) == ['two_factor_off', 'recovery_codes_renewed', 'two_factor_new_app', 'two_factor_on']


def test_refused_changes_are_not_logged(app, klara, secret, clock):
    new_app(app, klara, clock.code(secret), password='not it')
    app.simulate_post('/api/auth/me/two-factor/off', cookies=klara, json={'password': 'not it'})
    assert own_log(app, klara) == ['two_factor_on']
