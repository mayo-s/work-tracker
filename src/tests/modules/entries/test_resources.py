import datetime as dt

import falcon
import pytest

from src.models.entries import TicketEntry
from src.models.review import FlagReason
from src.modules.storage.catalog import ActivityTypeRepository, ServiceRepository
from src.modules.storage.entries import EntryRepository
from src.tests.users import USER

TICKET = {'kind': 'ticket', 'date': '2026-10-27', 'duration': '0:30', 'ticket_key': 'TNG-5882', 'description': 'PR Review',
          'coding': True}


@pytest.fixture
def ids(database):
    with database.transaction() as conn:
        services = {service.short_name: service.id for service in ServiceRepository(conn, USER).all()}
        activities = {activity.name: activity.id for activity in ActivityTypeRepository(conn, USER).all()}
    return services | activities


def create(client, body):
    result = client.simulate_post('/api/entries', json=body)
    assert result.status == falcon.HTTP_201
    return result.json


def test_create_ticket_entry(client):
    result = client.simulate_post('/api/entries', json=TICKET)
    assert result.status == falcon.HTTP_201
    assert result.headers['location'] == f'/api/entries/{result.json["id"]}'
    assert (result.json['ticket_key'], result.json['duration'], result.json['service'], result.json['changed']) == (
        'TNG-5882', '0:30', None, False)


def test_create_activity_entry(client, ids):
    body = {'kind': 'activity', 'date': '2026-10-28', 'duration': '4:00', 'activity_type_id': ids['Tool Management']}
    entry = create(client, body)
    assert (entry['activity_type'], entry['ticket_key'], entry['description']) == ('Tool Management', None, None)


def test_service_is_remembered_by_the_ticket(client, ids):
    create(client, TICKET | {'service_id': ids['MSB']})
    later = create(client, TICKET | {'date': '2026-10-28'})
    assert (later['service_id'], later['service']) == (ids['MSB'], 'MSB')
    ticket = client.simulate_get('/api/tickets/tng-5882').json
    assert ticket == {'key': 'TNG-5882', 'service_id': ids['MSB'], 'service': 'MSB', 'entries': 2}


def test_changing_the_service_applies_to_all_entries_of_the_ticket(client, ids):
    first = create(client, TICKET | {'service_id': ids['MSB']})
    create(client, TICKET | {'date': '2026-10-28', 'service_id': ids['HiS']})
    assert client.simulate_get(f'/api/entries/{first["id"]}').json['service'] == 'HiS'


def test_unknown_service_rolls_back_the_entry(client):
    assert client.simulate_post('/api/entries', json=TICKET | {'service_id': 404}).status == falcon.HTTP_409
    assert client.simulate_get('/api/entries', params={'week': '2026-W44'}).json == []


def test_unknown_activity_type(client):
    body = {'kind': 'activity', 'date': '2026-10-28', 'duration': '1:00', 'activity_type_id': 404}
    assert client.simulate_post('/api/entries', json=body).status == falcon.HTTP_409


@pytest.mark.parametrize('body', [
    {'kind': 'ticket', 'date': '2026-10-27', 'duration': '0:30'},
    TICKET | {'duration': '0:20'},
    TICKET | {'ticket_key': '#4138'},
])
def test_create_rejects_invalid_entry(client, body):
    assert client.simulate_post('/api/entries', json=body).status_code == 422


def test_list_entries_of_a_week(client, ids):
    create(client, TICKET | {'date': '2026-11-02'})
    create(client, TICKET)
    create(client, {'kind': 'activity', 'date': '2026-10-26', 'duration': '1:00', 'activity_type_id': ids['Meeting']})
    entries = client.simulate_get('/api/entries', params={'week': '2026-W44'}).json
    assert [(entry['date'], entry['kind']) for entry in entries] == [('2026-10-26', 'activity'), ('2026-10-27', 'ticket')]


def test_update_entry_marks_it_changed(client):
    created = create(client, TICKET)
    result = client.simulate_put(f'/api/entries/{created["id"]}', json=TICKET | {'duration': '1:00'})
    assert result.status == falcon.HTTP_200
    assert (result.json['duration'], result.json['changed']) == ('1:00', True)


def test_update_cannot_change_kind(client, ids):
    created = create(client, TICKET)
    body = {'kind': 'activity', 'date': '2026-10-27', 'duration': '0:30', 'activity_type_id': ids['Meeting']}
    assert client.simulate_put(f'/api/entries/{created["id"]}', json=body).status == falcon.HTTP_409


def test_update_missing_entry(client):
    assert client.simulate_put('/api/entries/404', json=TICKET).status == falcon.HTTP_404


def test_get_missing_entry(client):
    assert client.simulate_get('/api/entries/404').status == falcon.HTTP_404


def test_delete_entry_keeps_history(client):
    created = create(client, TICKET)
    client.simulate_put(f'/api/entries/{created["id"]}', json=TICKET | {'duration': '1:00'})
    assert client.simulate_delete(f'/api/entries/{created["id"]}').status == falcon.HTTP_204
    assert client.simulate_get(f'/api/entries/{created["id"]}').status == falcon.HTTP_404
    history = client.simulate_get(f'/api/entries/{created["id"]}/history').json
    assert [change['action'] for change in history] == ['created', 'updated', 'deleted']
    assert history[1]['changes'] == {'duration': [30, 60]}


def test_delete_missing_entry(client):
    assert client.simulate_delete('/api/entries/404').status == falcon.HTTP_404


def test_entry_shows_its_flags(client, database):
    created = create(client, TICKET)
    with database.transaction() as conn:
        EntryRepository(conn, USER).add_flag(created['id'], FlagReason.UNCERTAIN_TICKET, '#4138')
    [flag] = client.simulate_get(f'/api/entries/{created["id"]}').json['flags']
    assert (flag['reason'], flag['detail']) == ('uncertain_ticket', '#4138')


def test_history_of_unknown_entry_is_empty(client):
    assert client.simulate_get('/api/entries/404/history').json == []


def test_imported_entry_without_ticket_must_get_one_when_changed(client, database):
    with database.transaction() as conn:
        created = EntryRepository(conn, USER).create(TicketEntry(date=dt.date(2025, 11, 26), duration=360, coding=True))
    body = {'kind': 'ticket', 'date': '2025-11-26', 'duration': '6:00', 'coding': True}
    assert client.simulate_put(f'/api/entries/{created.id}', json=body).status_code == 422
    result = client.simulate_put(f'/api/entries/{created.id}', json=body | {'ticket_key': 'TNG-5096'})
    assert result.json['ticket_key'] == 'TNG-5096'


def test_split_entry(client):
    body = TICKET | {'ticket_key': 'TNG-4347', 'duration': '6:00', 'description': 'adapt tests (aka KP-1482)'}
    created = create(client, body)
    result = client.simulate_post(f'/api/entries/{created["id"]}/split', json={'ticket_keys': ['TNG-4347', 'kp-1482']})
    assert result.status == falcon.HTTP_200
    assert [(entry['ticket_key'], entry['duration'], entry['changed']) for entry in result.json] == [
        ('TNG-4347', '3:00', True), ('KP-1482', '3:00', True)]  # both point to the split in their history
    history = client.simulate_get(f'/api/entries/{created["id"]}/history').json
    assert (history[-1]['action'], history[-1]['detail']) == ('split', 'Split into TNG-4347, KP-1482')


@pytest.mark.parametrize('entry_id, body, status', [
    (404, {'ticket_keys': ['TNG-1', 'TNG-2']}, 404),
    (None, {'ticket_keys': ['TNG-4347']}, 422),
    (None, {'ticket_keys': ['TNG-4347', '#1482']}, 422),
    (None, {'ticket_keys': ['TNG-4347', 'tng-4347']}, 409),
])
def test_split_errors(client, entry_id, body, status):
    created = create(client, TICKET | {'ticket_key': 'TNG-4347'})
    path = f'/api/entries/{entry_id or created["id"]}/split'
    assert client.simulate_post(path, json=body).status_code == status


@pytest.mark.parametrize('duration, saved', [('1.5', '1:30'), ('1,25', '1:15'), ('1h30m', '1:30'), ('45m', '0:45')])
def test_durations_in_other_formats(client, duration, saved):
    assert create(client, TICKET | {'duration': duration})['duration'] == saved


def test_entry_fits_the_rest_of_its_day(client):
    client.simulate_put('/api/days/2026-10-27', json={'start': '08:00', 'end': '16:30'})
    assert client.simulate_post('/api/entries', json=TICKET | {'duration': '16h'}).status == falcon.HTTP_201
    refused = client.simulate_post('/api/entries', json=TICKET | {'duration': '16h15m'})
    assert (refused.status, refused.json['description']) == (
        falcon.HTTP_409, 'Longer than the day allows: at most 16:00 from 08:00 on')


def test_entry_change_fits_the_day_too(client):
    client.simulate_put('/api/days/2026-10-27', json={'start': '20:00', 'end': '23:00'})
    entry = create(client, TICKET)
    changed = client.simulate_put(f'/api/entries/{entry["id"]}', json=TICKET | {'duration': '4:15'})
    assert changed.status == falcon.HTTP_409
