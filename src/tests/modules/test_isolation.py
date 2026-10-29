"""Every user works on their own data: nobody sees or changes another user's records, not even by a known id."""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.models.entries import TicketEntry
from src.models.review import FlagReason
from src.modules.storage.entries import EntryRepository
from src.modules.storage.users import UserRepository
from src.tests.users import HANS, PASSWORD, USER


@pytest.fixture
def app(database):
    with database.transaction() as conn:
        UserRepository(conn).add(HANS, PASSWORD)
    return testing.TestClient(create_app(database, auth=True))


def logged_in(app, name):
    result = app.simulate_post('/api/auth/login', json={'login': name, 'password': PASSWORD})
    return {'wt_session': result.cookies['wt_session'].value}


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


def test_entries_of_others_are_unknown(app, klara, hans):
    body = {'kind': 'ticket', 'date': '2026-10-28', 'duration': '1:00', 'ticket_key': 'TNG-1', 'description': 'secret'}
    entry = app.simulate_post('/api/entries', cookies=klara, json=body).json
    path = f'/api/entries/{entry["id"]}'
    assert app.simulate_get(path, cookies=hans).status == falcon.HTTP_404
    assert app.simulate_put(path, cookies=hans, json=body | {'description': 'changed'}).status == falcon.HTTP_404
    assert app.simulate_delete(path, cookies=hans).status == falcon.HTTP_404
    assert app.simulate_get(f'{path}/history', cookies=hans).json == []
    assert app.simulate_get('/api/entries', cookies=hans, params={'week': '2026-W44'}).json == []
    assert app.simulate_get(path, cookies=klara).json['description'] == 'secret'


def test_lists_are_per_user(app, klara, hans):
    assert app.simulate_get('/api/services', cookies=hans).json == []
    assert len(app.simulate_get('/api/services', cookies=klara).json) == 5
    assert app.simulate_get(f'/api/services/{service_id(app, klara, "MSB")}', cookies=hans).status == falcon.HTTP_404
    assert app.simulate_post('/api/services', cookies=hans, json={'short_name': 'MSB'}).status == falcon.HTTP_201  # own list


def test_others_services_and_activity_types_cannot_be_used(app, klara, hans):
    msb = service_id(app, klara, 'MSB')
    meeting = app.simulate_get('/api/activity-types', cookies=klara).json[1]['id']
    ticket = {'kind': 'ticket', 'date': '2026-10-28', 'duration': '1:00', 'ticket_key': 'TNG-1', 'service_id': msb}
    assert app.simulate_post('/api/entries', cookies=hans, json=ticket).status == falcon.HTTP_409
    activity = {'kind': 'activity', 'date': '2026-10-28', 'duration': '1:00', 'activity_type_id': meeting}
    assert app.simulate_post('/api/entries', cookies=hans, json=activity).status == falcon.HTTP_409


def test_tickets_and_review_are_per_user(app, database, klara, hans):
    with database.transaction() as conn:
        entries = EntryRepository(conn, USER)
        created = entries.create(TicketEntry(date=dt.date(2026, 10, 28), ticket_key='TNG-4138', duration=60))
        flag = entries.add_flag(created.id, FlagReason.UNCERTAIN_TICKET, '#4138')
    assert app.simulate_get('/api/tickets/TNG-4138', cookies=hans).status == falcon.HTTP_404
    assert set(app.simulate_get('/api/review', cookies=hans).json['counts'].values()) == {0}
    assert app.simulate_delete(f'/api/review/flags/{flag.id}', cookies=hans).status == falcon.HTTP_404
    assert app.simulate_get('/api/review', cookies=klara).json['counts']['entries'] == 1


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


def test_login_off_works_on_the_first_users_data(database):
    app = testing.TestClient(create_app(database, auth=False))
    assert len(app.simulate_get('/api/services').json) == 5
