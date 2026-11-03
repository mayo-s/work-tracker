import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.users import UserRepository
from src.tests.users import HANS, PASCAL, PASSWORD, USER

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


@pytest.fixture
def root_id(database):
    with database.transaction() as conn:
        return UserRepository(conn).add(PASCAL.model_copy(update={'role': 'root'}), PASSWORD).id


@pytest.fixture
def root(app, root_id):
    """Pascal, root, logged in."""
    return logged_in(app, 'pascal')


def change(app, cookies, user_id, **body):
    return app.simulate_put(f'/api/admin/users/{user_id}', cookies=cookies, json={'role': 'user', 'active': True} | body)


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
                             'last_login_at', 'team', 'team_role', 'must_change_password', 'two_factor'}
    assert users[1]['last_login_at'] == '2026-10-29T08:00:00'


def test_root_appoints_and_removes_admins(app, root, hans, hans_id):
    assert change(app, root, hans_id, role='admin').json['role'] == 'admin'
    assert app.simulate_get('/api/admin/users', cookies=hans).status == falcon.HTTP_200
    assert change(app, root, hans_id, role='user').json['role'] == 'user'


def test_admins_do_not_appoint_admins(app, klara, hans_id):
    result = change(app, klara, hans_id, role='admin')
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'Only root appoints and removes admins')


def test_root_helps_admins(app, root, hans_id):
    change(app, root, hans_id, role='admin')
    assert change(app, root, hans_id, role='admin', active=False).json['active'] is False
    assert change(app, root, hans_id, role='admin').json['active'] is True
    one_time = app.simulate_post(f'/api/admin/users/{hans_id}/one-time-password', cookies=root)
    assert one_time.status == falcon.HTTP_201


def test_admins_do_not_help_admins(app, root, klara, hans_id):
    change(app, root, hans_id, role='admin')
    result = change(app, klara, hans_id, role='admin', active=False)
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'Only root for admins may deactivate or '
                                                                            'reactivate them')
    result = app.simulate_post(f'/api/admin/users/{hans_id}/one-time-password', cookies=klara)
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'Only root for admins may set one-time '
                                                                            'passwords')


def test_root_leaves_users_to_the_admins(app, root, hans_id):
    result = change(app, root, hans_id, active=False)
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'Only admins for users may deactivate or '
                                                                            'reactivate them')
    result = app.simulate_post(f'/api/admin/users/{hans_id}/one-time-password', cookies=root)
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'Only admins for users may set one-time '
                                                                            'passwords')


@pytest.mark.parametrize('method, path, body', [
    ('GET', '/api/admin/teams', None), ('POST', '/api/admin/teams', {'name': 'Platform'}),
])
def test_teams_are_for_admins_not_root(app, root, method, path, body):
    result = app.simulate_request(method, path, cookies=root, json=body)
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'Only admins may do this')


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


@pytest.mark.parametrize('body', [{'role': 'admin', 'active': True}, {'role': 'user', 'active': False}])
def test_root_stays_as_it_is(app, klara, root_id, body):
    result = app.simulate_put(f'/api/admin/users/{root_id}', cookies=klara, json=body)
    assert (result.status, result.json['description']) == (falcon.HTTP_409, 'Root stays root and active')
    result = app.simulate_post(f'/api/admin/users/{root_id}/one-time-password', cookies=klara)
    assert (result.status, result.json['description']) == (falcon.HTTP_409, "Root's password is changed in its own settings")


def test_nobody_is_made_root(app, klara, hans_id):
    body = {'role': 'root', 'active': True}
    assert app.simulate_put(f'/api/admin/users/{hans_id}', cookies=klara, json=body).status_code == 422


def test_only_members_of_a_team_can_be_team_admins(app, klara, hans_id):
    body = {'role': 'user', 'team_role': 'team_admin', 'active': True}
    assert app.simulate_put(f'/api/admin/users/{hans_id}', cookies=klara, json=body).status == falcon.HTTP_409


def test_root_switches_registration_on(app, root):
    assert app.simulate_get('/api/admin/settings', cookies=root).json == {'registration': False}
    assert app.simulate_put('/api/admin/settings', cookies=root, json={'registration': True}).json == {'registration': True}
    assert app.simulate_get('/api/auth/status').json['registration'] is True


def test_admins_do_not_switch_registration(app, klara):
    result = app.simulate_put('/api/admin/settings', cookies=klara, json={'registration': True})
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'Only root may do this')


def test_admin_page(app, klara):
    assert app.simulate_get('/admin', cookies=klara).status == falcon.HTTP_200
