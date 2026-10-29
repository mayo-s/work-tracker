import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.users import UserRepository
from src.tests.users import HANS, PASSWORD, USER

NOW = dt.datetime(2026, 10, 29, 8, 0)
UNKNOWN = '00000000-0000-4000-8000-000000000404'


@pytest.fixture
def hans_id(database):
    with database.transaction() as conn:
        return UserRepository(conn).add(HANS, PASSWORD).id


@pytest.fixture
def app(database, hans_id):
    return testing.TestClient(create_app(database, auth=True, clock=lambda: NOW))


def login(app, name):
    return app.simulate_post('/api/auth/login', json={'login': name, 'password': PASSWORD})


def logged_in(app, name):
    return {'wt_session': login(app, name).cookies['wt_session'].value}


@pytest.fixture
def klara(app):
    """Klara, the admin, logged in."""
    return logged_in(app, 'klara')


@pytest.fixture
def hans(app):
    """Hans, a user, logged in."""
    return logged_in(app, 'hans')


@pytest.mark.parametrize('method, path, body', [
    ('GET', '/api/admin/users', None),
    ('PUT', f'/api/admin/users/{USER}', {'role': 'user', 'active': False}),
    ('GET', '/api/admin/settings', None),
    ('PUT', '/api/admin/settings', {'registration': True}),
])
def test_only_admins(app, hans, method, path, body):
    assert app.simulate_request(method, path, cookies=hans, json=body).status == falcon.HTTP_403


def test_users_with_their_account_only(app, klara, hans):
    users = app.simulate_get('/api/admin/users', cookies=klara).json
    accounts = [(user['username'], user['role'], user['active']) for user in users]
    assert accounts == [('klara', 'admin', True), ('hans', 'user', True)]
    assert set(users[1]) == {'id', 'username', 'email', 'first_name', 'last_name', 'role', 'active', 'registered_at',
                             'last_login_at', 'team'}
    assert users[1]['last_login_at'] == '2026-10-29T08:00:00'


def test_change_role(app, klara, hans, hans_id):
    changed = app.simulate_put(f'/api/admin/users/{hans_id}', cookies=klara, json={'role': 'admin', 'active': True})
    assert changed.json['role'] == 'admin'
    assert app.simulate_get('/api/admin/users', cookies=hans).status == falcon.HTTP_200


def test_deactivated_user_is_logged_out_and_refused(app, klara, hans, hans_id):
    app.simulate_put(f'/api/admin/users/{hans_id}', cookies=klara, json={'role': 'user', 'active': False})
    assert app.simulate_get('/api/days', cookies=hans, params={'week': '2026-W44'}).status == falcon.HTTP_401
    refused = login(app, 'hans')
    assert (refused.status, refused.json['description']) == (falcon.HTTP_403, 'This account is deactivated; ask an admin')
    app.simulate_put(f'/api/admin/users/{hans_id}', cookies=klara, json={'role': 'user', 'active': True})
    assert login(app, 'hans').status == falcon.HTTP_200


@pytest.mark.parametrize('body', [{'role': 'user', 'active': True}, {'role': 'admin', 'active': False}])
def test_nobody_demotes_or_deactivates_themselves(app, klara, body):
    assert app.simulate_put(f'/api/admin/users/{USER}', cookies=klara, json=body).status == falcon.HTTP_409


def test_unknown_user(app, klara):
    body = {'role': 'user', 'active': True}
    assert app.simulate_put(f'/api/admin/users/{UNKNOWN}', cookies=klara, json=body).status == falcon.HTTP_404


def test_only_members_of_a_team_can_be_team_admins(app, klara, hans_id):
    body = {'role': 'team_admin', 'active': True}
    assert app.simulate_put(f'/api/admin/users/{hans_id}', cookies=klara, json=body).status == falcon.HTTP_409


def test_registration_is_off_until_switched_on(app, klara):
    assert app.simulate_get('/api/admin/settings', cookies=klara).json == {'registration': False}
    assert app.simulate_put('/api/admin/settings', cookies=klara, json={'registration': True}).json == {'registration': True}
    assert app.simulate_get('/api/auth/status').json['registration'] is True


def test_admin_page(app, klara):
    assert app.simulate_get('/admin', cookies=klara).status == falcon.HTTP_200
