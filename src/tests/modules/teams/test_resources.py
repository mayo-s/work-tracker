import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.users import UserRepository
from src.tests.users import HANS, PASSWORD, RAINER

NOW = dt.datetime(2026, 11, 2, 9, 0)
INVITED = {'message': 'If a user with this e-mail address exists, they find the invitation in their settings'}


@pytest.fixture
def app(database):
    with database.transaction() as conn:
        for person in (HANS, RAINER):
            UserRepository(conn).add(person, PASSWORD)
    return testing.TestClient(create_app(database, auth=True, clock=lambda: NOW))


def logged_in(app, name):
    result = app.simulate_post('/api/auth/login', json={'login': name, 'password': PASSWORD})
    return {'wt_session': result.cookies['wt_session'].value}


@pytest.fixture
def klara(app):
    """Klara, the admin."""
    return logged_in(app, 'klara')


@pytest.fixture
def hans(app):
    return logged_in(app, 'hans')


@pytest.fixture
def rainer(app):
    return logged_in(app, 'rainer')


@pytest.fixture
def team_id(app, klara):
    return app.simulate_post('/api/admin/teams', cookies=klara, json={'name': 'Platform'}).json['id']


def invite(app, cookies, team_id, email):
    return app.simulate_post(f'/api/teams/{team_id}/invitations', cookies=cookies, json={'email': email})


def join(app, inviter, team_id, email, cookies):
    """Invite the user with this e-mail address and let them accept."""
    invite(app, inviter, team_id, email)
    invitation = app.simulate_get('/api/team', cookies=cookies).json['invitations'][0]
    return app.simulate_post(f'/api/team/invitations/{invitation["id"]}/accept', cookies=cookies)


def user_id(app, cookies):
    return app.simulate_get('/api/auth/me', cookies=cookies).json['id']


@pytest.fixture
def hans_team_admin(app, klara, hans, team_id):
    """Hans joined the team, and the admin made him its team admin."""
    join(app, klara, team_id, 'hans.dampf@example.com', hans)
    app.simulate_put(f'/api/admin/users/{user_id(app, hans)}', cookies=klara, json={'role': 'team_admin', 'active': True})


def test_admin_manages_teams(app, klara, team_id):
    app.simulate_post('/api/admin/teams', cookies=klara, json={'name': 'Billing'})
    assert app.simulate_post('/api/admin/teams', cookies=klara, json={'name': 'platform'}).status == falcon.HTTP_409
    renamed = app.simulate_put(f'/api/admin/teams/{team_id}', cookies=klara, json={'name': 'Core'}).json
    assert (renamed['name'], renamed['members'], renamed['team_admins']) == ('Core', 0, [])
    assert app.simulate_delete(f'/api/admin/teams/{team_id}', cookies=klara).status == falcon.HTTP_204
    assert [team['name'] for team in app.simulate_get('/api/admin/teams', cookies=klara).json] == ['Billing']


def test_users_never_see_which_teams_exist(app, hans, team_id):
    assert app.simulate_get('/api/admin/teams', cookies=hans).status == falcon.HTTP_403
    assert app.simulate_get(f'/api/teams/{team_id}', cookies=hans).status == falcon.HTTP_403


def test_invitations_do_not_tell_whether_the_user_exists(app, klara, team_id):
    assert invite(app, klara, team_id, 'nobody@example.com').json == INVITED
    assert invite(app, klara, team_id, 'Hans.Dampf@Example.com').json == INVITED


def test_invited_user_sees_and_accepts_the_invitation(app, klara, hans, team_id):
    invite(app, klara, team_id, 'Hans.Dampf@Example.com')
    assert app.simulate_get('/api/auth/status', cookies=hans).json['invitations'] == 1
    invitation = app.simulate_get('/api/team', cookies=hans).json['invitations'][0]
    assert (invitation['team_name'], invitation['invited_by']) == ('Platform', 'Klara Himmel')
    joined = app.simulate_post(f'/api/team/invitations/{invitation["id"]}/accept', cookies=hans).json
    team = {'id': team_id, 'name': 'Platform', 'joined_on': '2026-11-02'}
    assert joined == {'team': team, 'invitations': [], 'team_admins': [], 'viewed_by': []}
    status = app.simulate_get('/api/auth/status', cookies=hans).json
    assert (status['team']['name'], status['invitations']) == ('Platform', 0)


def test_decline_and_withdraw(app, klara, hans, rainer, team_id):
    invite(app, klara, team_id, 'hans.dampf@example.com')
    invite(app, klara, team_id, 'rainer.zufall@example.com')
    invitation = app.simulate_get('/api/team', cookies=hans).json['invitations'][0]
    assert app.simulate_delete(f'/api/team/invitations/{invitation["id"]}', cookies=hans).status == falcon.HTTP_204
    open_ = app.simulate_get(f'/api/teams/{team_id}', cookies=klara).json['invitations']
    assert [entry['email'] for entry in open_] == ['rainer.zufall@example.com']
    app.simulate_delete(f'/api/teams/{team_id}/invitations/{open_[0]["id"]}', cookies=klara)
    assert app.simulate_get('/api/team', cookies=rainer).json['invitations'] == []


def test_others_cannot_accept_an_invitation(app, klara, hans, rainer, team_id):
    invite(app, klara, team_id, 'hans.dampf@example.com')
    invitation = app.simulate_get('/api/team', cookies=hans).json['invitations'][0]
    accepted = app.simulate_post(f'/api/team/invitations/{invitation["id"]}/accept', cookies=rainer)
    assert accepted.status == falcon.HTTP_404


def test_team_admin_manages_their_team_only(app, klara, hans, rainer, team_id, hans_team_admin):
    other = app.simulate_post('/api/admin/teams', cookies=klara, json={'name': 'Billing'}).json['id']
    assert invite(app, hans, team_id, 'rainer.zufall@example.com').status == falcon.HTTP_202
    assert invite(app, hans, other, 'rainer.zufall@example.com').status == falcon.HTTP_403
    assert app.simulate_get('/api/admin/teams', cookies=hans).status == falcon.HTTP_403
    members = app.simulate_get(f'/api/teams/{team_id}', cookies=hans).json['members']
    assert [(member['username'], member['role']) for member in members] == [('hans', 'team_admin')]
    assert set(members[0]) == {'user_id', 'username', 'email', 'first_name', 'last_name', 'role', 'joined_on'}


def test_members_choose_team_services_that_only_team_admins_change(app, klara, hans, rainer, team_id, hans_team_admin):
    join(app, hans, team_id, 'rainer.zufall@example.com', rainer)
    service = app.simulate_post(f'/api/teams/{team_id}/services', cookies=hans, json={'short_name': 'AUTH'}).json
    assert app.simulate_post(f'/api/teams/{team_id}/services', cookies=rainer, json={'short_name': 'X'}).status \
        == falcon.HTTP_403
    choices = app.simulate_get('/api/service-choices', cookies=rainer).json
    assert choices == [{'id': service['id'], 'short_name': 'AUTH', 'name': '', 'team': 'Platform'}]
    entry = {'kind': 'ticket', 'date': '2026-11-02', 'duration': '1:00', 'ticket_key': 'TNG-1', 'service_id': service['id']}
    assert app.simulate_post('/api/entries', cookies=rainer, json=entry).json['service'] == 'AUTH'


def test_removed_member_keeps_the_service_of_their_tickets(app, klara, hans, rainer, team_id, hans_team_admin):
    join(app, hans, team_id, 'rainer.zufall@example.com', rainer)
    service = app.simulate_post(f'/api/teams/{team_id}/services', cookies=hans, json={'short_name': 'AUTH'}).json
    entry = {'kind': 'ticket', 'date': '2026-11-02', 'duration': '1:00', 'ticket_key': 'TNG-1', 'service_id': service['id']}
    app.simulate_post('/api/entries', cookies=rainer, json=entry)
    removed = app.simulate_delete(f'/api/teams/{team_id}/members/{user_id(app, rainer)}', cookies=hans)
    assert removed.status == falcon.HTTP_204
    assert app.simulate_get('/api/team', cookies=rainer).json['team'] is None
    assert app.simulate_get('/api/tickets/TNG-1', cookies=rainer).json['service'] == 'AUTH'
    assert [service['team'] for service in app.simulate_get('/api/service-choices', cookies=rainer).json] == [None]


def test_team_admin_leaving_becomes_a_user(app, klara, hans, team_id, hans_team_admin):
    assert app.simulate_delete('/api/team', cookies=hans).status == falcon.HTTP_204
    users = {user['username']: user for user in app.simulate_get('/api/admin/users', cookies=klara).json}
    assert (users['hans']['role'], users['hans']['team']) == ('user', None)
    assert app.simulate_get(f'/api/teams/{team_id}', cookies=hans).status == falcon.HTTP_403


def test_team_with_members_is_not_deleted(app, klara, hans, team_id, hans_team_admin):
    assert app.simulate_delete(f'/api/admin/teams/{team_id}', cookies=klara).status == falcon.HTTP_409


def test_admin_list_shows_the_team(app, klara, team_id, hans_team_admin):
    users = {user['username']: user for user in app.simulate_get('/api/admin/users', cookies=klara).json}
    assert (users['hans']['team'], users['hans']['role'], users['klara']['team']) == ('Platform', 'team_admin', None)
    teams = app.simulate_get('/api/admin/teams', cookies=klara).json
    assert (teams[0]['members'], teams[0]['team_admins']) == (1, ['hans'])


def test_team_page(app, klara):
    assert app.simulate_get('/team', cookies=klara).status == falcon.HTTP_200
