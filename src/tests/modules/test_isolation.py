"""Every user works on their own data: nobody sees or changes another user's records, not even by a known id (SPEC 5.7,
7.3). The whole app runs on SQLite and on DynamoDB (moto)."""

import datetime as dt
from decimal import Decimal

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.models.catalog import Service
from src.models.entries import Entry
from src.models.pto import PtoYear
from src.models.review import FlagReason
from src.models.schedules import Schedule
from src.models.settings import Settings
from src.tests.helpers import logged_in
from src.tests.ids import FIRST
from src.tests.users import HANS, KLARA, PASSWORD


@pytest.fixture
def klara_id(storage):
    """Klara, set up as in the original setup (services, schedule, PTO years), and Hans, a new user."""
    with storage.transaction() as store:
        klara = store.users().add(KLARA, PASSWORD).id
        store.users().add(HANS, PASSWORD)
        for short_name in ('O365', 'MSB', 'ImmoDrop', 'HiS', 'TTS'):
            store.services(klara).add(Service(short_name=short_name))
        store.schedules(klara).replace_all(
            Schedule(valid_from=dt.date(2024, 6, 1), weekly_minutes=2400, work_days=[1, 2, 3, 4, 5]))
        store.pto_years(klara).replace_all([PtoYear(year=2026, allowance=Decimal(31))])
        store.save_settings(klara, Settings(balance_start=dt.date(2024, 6, 1)))
        store.finish_setup(klara)
    return klara


@pytest.fixture
def app(storage, klara_id):
    return testing.TestClient(create_app(storage=storage, auth=True))


@pytest.fixture
def klara(app):
    return logged_in(app, 'klara')


@pytest.fixture
def hans(app):
    return logged_in(app, 'hans')


def service_id(app, cookies, short_name):
    return next(service['id'] for service in app.simulate_get('/api/services', cookies=cookies).json
                if service['short_name'] == short_name)


def test_days_are_per_user(app, klara, hans):
    app.simulate_put('/api/days/2026-10-28', cookies=klara, json={'day_type': 'pto'})
    assert app.simulate_get('/api/days/2026-10-28', cookies=hans).json['recorded'] is False
    app.simulate_put('/api/days/2026-10-28', cookies=hans, json={'start': '08:00', 'end': '16:30'})
    assert app.simulate_get('/api/days/2026-10-28', cookies=klara).json['day_type'] == 'pto'
    assert app.simulate_delete('/api/days/2026-10-29', cookies=hans).status == falcon.HTTP_404


def test_lists_are_per_user(app, klara, hans):
    assert app.simulate_get('/api/services', cookies=hans).json == []
    assert len(app.simulate_get('/api/services', cookies=klara).json) == 5
    assert app.simulate_post('/api/services', cookies=hans, json={'short_name': 'MSB'}).status == falcon.HTTP_201  # own list


def test_others_services_and_activity_types_cannot_be_used(app, klara, hans):
    msb = service_id(app, klara, 'MSB')
    meeting = app.simulate_get('/api/activity-types', cookies=klara).json[1]['id']
    own = app.simulate_get('/api/activity-types', cookies=hans).json[0]['id']
    ticket = {'activity_type_id': own, 'date': '2026-10-28', 'duration': '1:00', 'ticket_key': 'TNG-1', 'service_id': msb}
    assert app.simulate_post('/api/entries', cookies=hans, json=ticket).status == falcon.HTTP_409
    activity = {'date': '2026-10-28', 'duration': '1:00', 'activity_type_id': meeting}
    assert app.simulate_post('/api/entries', cookies=hans, json=activity).status == falcon.HTTP_409


def test_review_is_per_user(app, storage, klara_id, klara, hans):
    with storage.transaction() as store:
        entries = store.entries(klara_id)
        entries.add_flag(entries.create(Entry(date=dt.date(2026, 10, 28), ticket_key='TNG-4138', duration=60)).id,
                         FlagReason.UNCERTAIN_TICKET, '#4138')
    assert set(app.simulate_get('/api/review', cookies=hans).json['counts'].values()) == {0}
    assert set(app.simulate_get('/api/review/counts', cookies=hans).json.values()) == {0}
    assert app.simulate_get('/api/review/counts', cookies=klara).json['entries'] == 1


def test_settings_schedules_and_pto_are_per_user(app, klara, hans):
    app.simulate_put('/api/theme', cookies=hans, json={'theme': 'dark'})
    app.simulate_put('/api/pto-years/2026', cookies=hans, json={'allowance': 25})
    assert app.simulate_get('/api/theme', cookies=klara).json == {'theme': 'system'}
    assert app.simulate_get('/api/pto-years/2026', cookies=klara).json['allowance'] == 31.0
    assert app.simulate_get('/api/work-schedules', cookies=hans).json == []
    assert len(app.simulate_get('/api/work-schedules', cookies=klara).json) == 1


def test_a_new_user_is_set_up_first(app, hans):
    result = app.simulate_get('/week', cookies=hans)
    assert (result.status, result.headers['location']) == (falcon.HTTP_303, '/setup')
    body = {'balance_start': '2026-11-02', 'schedule': {'weekly_hours': '30:00', 'work_days': ['Mon', 'Tue', 'Wed', 'Thu']},
            'pto_first_year': 5}
    assert app.simulate_post('/api/setup', cookies=hans, json=body).json == {'done': True}
    assert app.simulate_get('/week', cookies=hans).status == falcon.HTTP_200
    assert app.simulate_get('/api/settings', cookies=hans).json['balance_start'] == '2026-11-02'


def test_login_off_works_on_the_first_users_data(storage, klara_id):
    app = testing.TestClient(create_app(storage=storage, auth=False))
    assert len(app.simulate_get('/api/services').json) == 5


@pytest.fixture
def klaras_records(app, storage, klara_id, klara):
    """One record of every kind with an id, all Klara's; Klara is admin and team admin of Platform."""
    planning = app.simulate_get('/api/activity-types', cookies=klara).json[2]['id']
    entry = app.simulate_post('/api/entries', cookies=klara, json={
        'activity_type_id': planning, 'date': '2026-10-28', 'duration': '1:00', 'ticket_key': 'TNG-4138',
        'description': 'secret'}).json
    with storage.transaction() as store:
        flag = store.entries(klara_id).add_flag(entry['id'], FlagReason.UNCERTAIN_TICKET, '#4138')
    team = app.simulate_post('/api/admin/teams', cookies=klara, json={'name': 'Platform'}).json
    app.simulate_put(f'/api/admin/users/{klara_id}', cookies=klara, json={'role': 'admin', 'active': True})
    with storage.transaction() as store:
        store.teams().join(klara_id, team['id'])
        store.teams().set_team_role(klara_id, 'team_admin')
    app.simulate_post(f'/api/teams/{team["id"]}/invitations', cookies=klara, json={'email': 'rainer.zufall@example.com'})
    with storage.transaction() as store:
        invitation = store.invitations().of_team(team['id'])[0]
    records = {
        'entry': entry['id'], 'flag': flag.id, 'service': service_id(app, klara, 'MSB'), 'team': team['id'],
        'activity_type': app.simulate_get('/api/activity-types', cookies=klara).json[0]['id'],
        'schedule': app.simulate_get('/api/work-schedules', cookies=klara).json[0]['id'],
        'team_service': app.simulate_post(f'/api/teams/{team["id"]}/services', cookies=klara,
                                          json={'short_name': 'AUTH'}).json['id'],
        'invitation': invitation.id, 'klara': klara_id,
    }
    return records


SERVICE = {'short_name': 'MSB', 'name': 'changed'}
ENTRY = {'activity_type_id': FIRST, 'date': '2026-10-28', 'duration': '2:00', 'ticket_key': 'TNG-4138'}
SCHEDULE = {'valid_from': '2027-01-01', 'weekly_hours': '20:00', 'work_days': ['Mon']}

# Hans tries every route with an id of one of Klara's records, and what he should get: unknown to him (404) or not his
# to manage (403)
ATTEMPTS = [
    ('GET', '/api/entries/{entry}', None, falcon.HTTP_404),
    ('PUT', '/api/entries/{entry}', ENTRY, falcon.HTTP_404),
    ('DELETE', '/api/entries/{entry}', None, falcon.HTTP_404),
    ('GET', '/api/entries/{entry}/history', None, falcon.HTTP_404),
    ('POST', '/api/entries/{entry}/split', {'ticket_keys': ['TNG-1', 'TNG-2']}, falcon.HTTP_404),
    ('GET', '/api/tickets/TNG-4138', None, falcon.HTTP_404),
    ('PUT', '/api/tickets/TNG-4138', {'service_id': None}, falcon.HTTP_404),
    ('POST', '/api/tickets/TNG-4138/rename', {'new_key': 'KP-4138'}, falcon.HTTP_404),
    ('DELETE', '/api/review/flags/{flag}', None, falcon.HTTP_404),
    ('GET', '/api/services/{service}', None, falcon.HTTP_404),
    ('PUT', '/api/services/{service}', SERVICE, falcon.HTTP_404),
    ('DELETE', '/api/services/{service}', None, falcon.HTTP_404),
    ('GET', '/api/activity-types/{activity_type}', None, falcon.HTTP_404),
    ('PUT', '/api/activity-types/{activity_type}', {'name': 'changed'}, falcon.HTTP_404),
    ('DELETE', '/api/activity-types/{activity_type}', None, falcon.HTTP_404),
    ('GET', '/api/work-schedules/{schedule}', None, falcon.HTTP_404),
    ('PUT', '/api/work-schedules/{schedule}', SCHEDULE, falcon.HTTP_404),
    ('DELETE', '/api/work-schedules/{schedule}', None, falcon.HTTP_404),
    ('GET', '/api/pto-years/2026', None, falcon.HTTP_404),
    ('DELETE', '/api/pto-years/2026', None, falcon.HTTP_404),
    ('DELETE', '/api/team/invitations/{invitation}', None, falcon.HTTP_404),
    ('POST', '/api/team/invitations/{invitation}/accept', None, falcon.HTTP_404),
    ('GET', '/api/teams/{team}', None, falcon.HTTP_403),
    ('POST', '/api/teams/{team}/invitations', {'email': 'hans.dampf@example.com'}, falcon.HTTP_403),
    ('DELETE', '/api/teams/{team}/invitations/{invitation}', None, falcon.HTTP_403),
    ('DELETE', '/api/teams/{team}/members/{klara}', None, falcon.HTTP_403),
    ('GET', '/api/teams/{team}/services', None, falcon.HTTP_403),
    ('POST', '/api/teams/{team}/services', SERVICE, falcon.HTTP_403),
    ('PUT', '/api/teams/{team}/services/{team_service}', SERVICE, falcon.HTTP_403),
    ('DELETE', '/api/teams/{team}/services/{team_service}', None, falcon.HTTP_403),
    ('PUT', '/api/admin/teams/{team}', {'name': 'Taken'}, falcon.HTTP_403),
    ('DELETE', '/api/admin/teams/{team}', None, falcon.HTTP_403),
    ('PUT', '/api/admin/users/{klara}', {'role': 'user', 'active': False}, falcon.HTTP_403),
    ('GET', '/api/dashboard?member={klara}', None, falcon.HTTP_403),
    ('GET', '/api/reports/years/2026?member={klara}', None, falcon.HTTP_403),
    ('GET', '/api/days?week=2026-W44&member={klara}', None, falcon.HTTP_403),
]


def test_records_of_others_are_unknown_or_not_to_manage_and_stay_as_they_were(app, klaras_records, klara, hans):
    actual = {}
    for method, path, body, _ in ATTEMPTS:
        route, _, query = path.format(**klaras_records).partition('?')
        actual[f'{method} {path}'] = app.simulate_request(method, route, query_string=query, cookies=hans, json=body).status
    assert actual == {f'{method} {path}': status for method, path, _, status in ATTEMPTS}
    records = klaras_records
    assert app.simulate_get(f'/api/entries/{records["entry"]}', cookies=klara).json['description'] == 'secret'
    assert app.simulate_get(f'/api/services/{records["service"]}', cookies=klara).json['name'] == ''
    assert app.simulate_get(f'/api/work-schedules/{records["schedule"]}', cookies=klara).status == falcon.HTTP_200
    assert app.simulate_get('/api/pto-years/2026', cookies=klara).json['allowance'] == 31.0
    assert app.simulate_get(f'/api/teams/{records["team"]}', cookies=klara).json['name'] == 'Platform'
    assert len(app.simulate_get('/api/review', cookies=klara).json['entries']) == 1
    assert app.simulate_get('/api/auth/me', cookies=klara).json['role'] == 'admin'
    assert app.simulate_get('/api/auth/status', cookies=klara).json['team']['team_role'] == 'team_admin'
