"""Two-factor login is required for root and admins (SPEC 5.6, TASKS.md 9.1g2): until set up, every page forwards to
/2fa; it cannot be switched off; admins reset it for users, root for admins, root its own with a new setup token."""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.lib.totp import code_at, time_step
from src.modules.storage.users import UserRepository
from src.tests.helpers import logged_in, login, session
from src.tests.users import HANS, PASCAL, PASSWORD

NOW = dt.datetime(2026, 11, 2, 9, 0)


@pytest.fixture
def ids(database, two_factor_required):
    with database.transaction() as conn:
        users = UserRepository(conn)
        return {'hans': users.add(HANS, PASSWORD).id,
                'pascal': users.add(PASCAL.model_copy(update={'role': 'root'}), PASSWORD).id}


@pytest.fixture
def app(database, ids):
    return testing.TestClient(create_app(database, auth=True, clock=lambda: NOW))


def switch_on(app, cookies, steps_later=0):
    """Two-factor login set up and confirmed; its secret."""
    secret = app.simulate_post('/api/auth/me/two-factor', cookies=cookies).json['secret']
    app.simulate_put('/api/auth/me/two-factor', cookies=cookies, json={'code': code_at(secret, time_step(NOW) + steps_later)})
    return secret


@pytest.mark.parametrize('name', ['klara', 'pascal'])
def test_root_and_admins_set_it_up_before_anything_else(app, name):
    cookies = logged_in(app, name)
    result = app.simulate_get('/admin', cookies=cookies)
    assert (result.status, result.headers['location']) == (falcon.HTTP_303, '/2fa')
    api = app.simulate_get('/api/admin/users', cookies=cookies)
    assert (api.status, api.json['description']) == (falcon.HTTP_403, 'Set up two-factor login first, on /2fa')
    assert app.simulate_get('/2fa', cookies=cookies).status == falcon.HTTP_200
    switch_on(app, cookies)
    assert app.simulate_get('/api/admin/users', cookies=cookies).status == falcon.HTTP_200


def test_users_choose(app):
    assert app.simulate_get('/api/dashboard', cookies=logged_in(app, 'hans')).status == falcon.HTTP_200


def test_root_and_admins_cannot_switch_it_off(app):
    klara = logged_in(app, 'klara')
    switch_on(app, klara)
    result = app.simulate_post('/api/auth/me/two-factor/off', cookies=klara, json={'password': PASSWORD})
    assert (result.status, result.json['description']) == (falcon.HTTP_409, 'Root and admins must use two-factor login')


def reset(app, cookies, user_id):
    return app.simulate_post(f'/api/admin/users/{user_id}/two-factor-reset', cookies=cookies)


def test_an_admin_resets_it_for_a_user(app, ids):
    hans = logged_in(app, 'hans')
    switch_on(app, hans)
    klara = logged_in(app, 'klara')
    switch_on(app, klara, steps_later=1)
    assert reset(app, klara, ids['hans']).status == falcon.HTTP_204
    assert app.simulate_get('/api/auth/me/two-factor', cookies=hans).json['enabled'] is False
    assert [entry['action'] for entry in app.simulate_get('/api/admin/audit', cookies=klara).json][0] == 'two_factor_reset'
    assert reset(app, klara, ids['hans']).status == falcon.HTTP_409  # off already


def test_root_resets_it_for_an_admin_and_the_admin_sets_it_up_again(app, database, ids):
    klara = logged_in(app, 'klara')
    switch_on(app, klara)
    root = logged_in(app, 'pascal')
    switch_on(app, root, steps_later=1)
    with database.transaction() as conn:
        klara_id = UserRepository(conn).by_login('klara').id
    assert reset(app, root, klara_id).status == falcon.HTTP_204
    assert app.simulate_get('/admin', cookies=klara).headers['location'] == '/2fa'


@pytest.mark.parametrize('name, target, message', [
    ('klara', 'pascal', 'Root resets its own login with a new setup token'),
    ('klara', 'klara', 'Not for your own account: log in with a recovery code instead'),
])
def test_refused(app, database, name, target, message):
    cookies = logged_in(app, name)
    switch_on(app, cookies)
    with database.transaction() as conn:
        target_id = UserRepository(conn).by_login(target).id
    result = reset(app, cookies, target_id)
    assert (result.status, result.json['description']) == (falcon.HTTP_409, message)


def test_admins_do_not_reset_admins(app, database, ids):
    with database.transaction() as conn:
        UserRepository(conn).set_role(ids['hans'], 'admin')
    klara = logged_in(app, 'klara')
    switch_on(app, klara)
    result = reset(app, klara, ids['hans'])
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'Only root for admins may reset two-factor '
                                                                            'login')


def test_root_has_an_hour_and_no_remembered_browser(app):
    first = login(app, 'pascal')
    assert first.cookies['wt_session'].max_age == 3600
    secret = switch_on(app, session(first))
    code = code_at(secret, time_step(NOW) + 1)
    result = login(app, 'pascal', code=code, remember=True)
    assert result.status == falcon.HTTP_200 and 'wt_browser' not in result.cookies


@pytest.mark.parametrize('name', ['klara', 'pascal'])
def test_root_and_admins_move_to_a_new_app(app, name):
    cookies = logged_in(app, name)
    secret = switch_on(app, cookies)
    started = app.simulate_post('/api/auth/me/two-factor/new-app', cookies=cookies,
                                json={'password': PASSWORD, 'code': code_at(secret, time_step(NOW) + 1)})
    fresh = started.json['secret']
    confirmed = app.simulate_put('/api/auth/me/two-factor/new-app', cookies=cookies,
                                 json={'code': code_at(fresh, time_step(NOW))})
    assert confirmed.status == falcon.HTTP_204
