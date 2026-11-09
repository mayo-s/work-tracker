"""The audit log through the API: every change of running the app is recorded, root and admins read it, every user
the entries about them."""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.tests.helpers import logged_in, session
from src.tests.users import PASSWORD

NOW = dt.datetime(2026, 11, 2, 9, 0)


@pytest.fixture
def app(database, people):
    return testing.TestClient(create_app(database, auth=True, clock=lambda: NOW))


def log(app, cookies):
    return [(entry['actor'], entry['action'], entry['user'], entry['team'], entry['detail'])
            for entry in app.simulate_get('/api/admin/audit', cookies=cookies).json]


def test_changes_of_root_and_admins_are_recorded(app, people):
    root, klara = logged_in(app, 'pascal'), logged_in(app, 'klara')
    hans = f'/api/admin/users/{people["hans"]}'
    app.simulate_put('/api/admin/settings', cookies=root, json={'registration': True})
    app.simulate_put(hans, cookies=root, json={'role': 'admin', 'active': True})
    app.simulate_put(hans, cookies=root, json={'role': 'user', 'active': True})
    app.simulate_put(hans, cookies=klara, json={'role': 'user', 'active': True, 'support': True})
    app.simulate_put(hans, cookies=klara, json={'role': 'user', 'active': False})
    app.simulate_post(f'{hans}/one-time-password', cookies=klara)
    team = app.simulate_post('/api/admin/teams', cookies=klara, json={'name': 'Platform'}).json['id']
    app.simulate_put(f'/api/admin/teams/{team}', cookies=klara, json={'name': 'Core'})
    app.simulate_delete(f'/api/admin/teams/{team}', cookies=klara)
    assert log(app, klara) == [
        ('Klara Himmel', 'team_deleted', None, 'Core', ''),
        ('Klara Himmel', 'team_renamed', None, 'Core', 'Platform'),
        ('Klara Himmel', 'team_created', None, 'Core', ''),
        ('Klara Himmel', 'one_time_password', 'Hans Dampf', None, ''),
        ('Klara Himmel', 'deactivated', 'Hans Dampf', None, ''),
        ('Klara Himmel', 'support_switched', 'Hans Dampf', None, 'on'),
        ('Pascal Turbo', 'role_changed', 'Hans Dampf', None, 'user'),
        ('Pascal Turbo', 'role_changed', 'Hans Dampf', None, 'admin'),
        ('Pascal Turbo', 'registration_switched', None, None, 'on'),
    ]


def test_nothing_is_recorded_without_a_change(app, people):
    root, klara = logged_in(app, 'pascal'), logged_in(app, 'klara')
    app.simulate_put('/api/admin/settings', cookies=root, json={'registration': False})
    app.simulate_put(f'/api/admin/users/{people["hans"]}', cookies=klara, json={'role': 'user', 'active': True})
    assert log(app, root) == []


def test_team_roles_and_removed_members(app, database, people):
    klara, hans = logged_in(app, 'klara'), logged_in(app, 'hans')
    team = app.simulate_post('/api/admin/teams', cookies=klara, json={'name': 'Platform'}).json['id']
    app.simulate_post(f'/api/teams/{team}/invitations', cookies=klara, json={'email': 'hans.dampf@example.com'})
    invitation = app.simulate_get('/api/team', cookies=hans).json['invitations'][0]['id']
    app.simulate_post(f'/api/team/invitations/{invitation}/accept', cookies=hans)
    app.simulate_put(f'/api/admin/users/{people["hans"]}', cookies=klara,
                     json={'role': 'user', 'team_role': 'team_admin', 'active': True})
    app.simulate_delete(f'/api/teams/{team}/members/{people["hans"]}', cookies=klara)
    assert log(app, klara)[:2] == [('Klara Himmel', 'member_removed', 'Hans Dampf', 'Platform', ''),
                                   ('Klara Himmel', 'team_role_changed', 'Hans Dampf', 'Platform', 'team_admin')]


def test_root_creation_is_recorded(fresh_database):
    app = testing.TestClient(create_app(fresh_database, auth=True, clock=lambda: NOW))
    root = app.simulate_post('/api/auth/root', json={'username': 'pascal', 'email': 'turbo.pascal@example.com',
                                                     'first_name': 'Pascal', 'last_name': 'Turbo', 'password': PASSWORD})
    cookies = session(root)
    assert log(app, cookies) == [('Pascal Turbo', 'root_created', 'Pascal Turbo', None, '')]


def test_each_user_sees_the_changes_to_their_account(app, people):
    root = logged_in(app, 'pascal')
    app.simulate_put(f'/api/admin/users/{people["hans"]}', cookies=root, json={'role': 'admin', 'active': True})
    app.simulate_put('/api/admin/settings', cookies=root, json={'registration': True})
    mine = app.simulate_get('/api/auth/me/audit', cookies=logged_in(app, 'hans')).json
    assert [(entry['actor'], entry['action'], entry['detail']) for entry in mine] == [
        ('Pascal Turbo', 'role_changed', 'admin')]
    assert app.simulate_get('/api/auth/me/audit', cookies=logged_in(app, 'klara')).json == []


def test_only_root_and_admins_read_the_whole_log(app, people):
    result = app.simulate_get('/api/admin/audit', cookies=logged_in(app, 'hans'))
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'Only root and admins may do this')
