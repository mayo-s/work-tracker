import datetime as dt

import falcon
import pytest

from src.models.entries import Entry
from src.models.review import FlagReason
from src.modules.storage.catalog import ActivityTypeRepository, ServiceRepository
from src.modules.storage.entries import EntryRepository
from src.tests.users import USER
from src.tests.ids import CODING, UNKNOWN

TICKET = {'date': '2026-10-27', 'activity_type_id': CODING, 'duration': '0:30', 'ticket_key': 'TNG-5882',
          'description': 'PR Review'}


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
    body = {'date': '2026-10-28', 'duration': '4:00', 'activity_type_id': ids['Planning']}
    entry = create(client, body)
    assert (entry['activity_type'], entry['ticket_key'], entry['description']) == ('Planning', None, '')


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
    assert client.simulate_post('/api/entries', json=TICKET | {'service_id': UNKNOWN}).status == falcon.HTTP_409
    assert client.simulate_get('/api/entries', params={'week': '2026-W44'}).json == []


def test_unknown_activity_type(client):
    body = {'date': '2026-10-28', 'duration': '1:00', 'activity_type_id': UNKNOWN}
    assert client.simulate_post('/api/entries', json=body).status == falcon.HTTP_409


def test_create_rejects_invalid_entry(client):
    assert client.simulate_post('/api/entries', json=TICKET | {'duration': '0:20'}).status_code == 422


def test_list_entries_of_a_week(client, ids):
    create(client, TICKET | {'date': '2026-11-02'})
    create(client, TICKET)
    create(client, {'date': '2026-10-26', 'duration': '1:00', 'activity_type_id': ids['Meeting']})
    entries = client.simulate_get('/api/entries', params={'week': '2026-W44'}).json
    actual = [(entry['date'], entry['activity_type']) for entry in entries]
    assert actual == [('2026-10-26', 'Meeting'), ('2026-10-27', 'Coding')]


def test_update_entry_marks_it_changed(client):
    created = create(client, TICKET)
    result = client.simulate_put(f'/api/entries/{created["id"]}', json=TICKET | {'duration': '1:00'})
    assert result.status == falcon.HTTP_200
    assert (result.json['duration'], result.json['changed']) == ('1:00', True)


def test_missing_entry(client):
    actual = {
        'get': client.simulate_get(f'/api/entries/{UNKNOWN}').status_code,
        'update': client.simulate_put(f'/api/entries/{UNKNOWN}', json=TICKET).status_code,
        'delete': client.simulate_delete(f'/api/entries/{UNKNOWN}').status_code,
        'history': client.simulate_get(f'/api/entries/{UNKNOWN}/history').status_code,
    }
    assert actual == {'get': 404, 'update': 404, 'delete': 404, 'history': 404}


def test_delete_entry_keeps_history(client):
    created = create(client, TICKET)
    client.simulate_put(f'/api/entries/{created["id"]}', json=TICKET | {'duration': '1:00'})
    assert client.simulate_delete(f'/api/entries/{created["id"]}').status == falcon.HTTP_204
    assert client.simulate_get(f'/api/entries/{created["id"]}').status == falcon.HTTP_404
    history = client.simulate_get(f'/api/entries/{created["id"]}/history').json
    assert [change['action'] for change in history] == ['created', 'updated', 'deleted']
    assert history[1]['changes'] == {'duration': [30, 60]}


def test_entry_shows_its_flags(client, database):
    created = create(client, TICKET)
    with database.transaction() as conn:
        EntryRepository(conn, USER).add_flag(created['id'], FlagReason.UNCERTAIN_TICKET, '#4138')
    [flag] = client.simulate_get(f'/api/entries/{created["id"]}').json['flags']
    assert (flag['reason'], flag['detail']) == ('uncertain_ticket', '#4138')


def test_imported_entry_without_ticket_must_get_one_when_changed(client, database):
    with database.transaction() as conn:
        created = EntryRepository(conn, USER).create(Entry(date=dt.date(2025, 11, 26), activity_type_id=CODING, duration=360))
    body = {'date': '2025-11-26', 'activity_type_id': CODING, 'duration': '6:00'}
    result = client.simulate_put(f'/api/entries/{created.id}', json=body)
    assert (result.status_code, result.json['description']) == (409, 'Coding needs a ticket')
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
    (UNKNOWN, {'ticket_keys': ['TNG-1', 'TNG-2']}, 404),
    (None, {'ticket_keys': ['TNG-4347']}, 422),
    (None, {'ticket_keys': ['TNG-4347', 'tng-4347']}, 409),
])
def test_split_errors(client, entry_id, body, status):
    created = create(client, TICKET | {'ticket_key': 'TNG-4347'})
    path = f'/api/entries/{entry_id or created["id"]}/split'
    assert client.simulate_post(path, json=body).status_code == status


def test_durations_in_other_formats(client):
    assert create(client, TICKET | {'duration': '1h15m'})['duration'] == '1:15'


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


def test_assign_an_activity_type_to_several_entries(client, database, ids):
    with database.transaction() as conn:
        entries = EntryRepository(conn, USER)
        former = [entries.create(Entry(date=dt.date(2026, 10, 27), ticket_key='TNG-1', duration=60)).id,
                  entries.create(Entry(date=dt.date(2026, 10, 28), duration=30)).id]  # no ticket
    body = {'entry_ids': [*former, former[0]], 'activity_type_id': ids['Planning']}
    assert client.simulate_post('/api/entries/assign-activity-type', json=body).json == {'assigned': 2}
    assert [client.simulate_get(f'/api/entries/{entry_id}').json['activity_type'] for entry_id in former] == [
        'Planning', 'Planning']
    [_, change] = client.simulate_get(f'/api/entries/{former[0]}/history').json
    assert (change['action'], change['changes']) == ('updated', {'activity_type_id': [None, ids['Planning']]})


@pytest.mark.parametrize('unknown, activity_type, status', [([UNKNOWN], 'Planning', 404), ([], 'Coding', 409)])
def test_an_assignment_that_fails_changes_nothing(client, database, ids, unknown, activity_type, status):
    with database.transaction() as conn:
        entries = EntryRepository(conn, USER)
        former = [entries.create(Entry(date=dt.date(2026, 10, 27), ticket_key='TNG-1', duration=60)).id,
                  entries.create(Entry(date=dt.date(2026, 10, 28), duration=30)).id]  # Coding needs a ticket
    body = {'entry_ids': [*former, *unknown], 'activity_type_id': ids[activity_type]}
    assert client.simulate_post('/api/entries/assign-activity-type', json=body).status_code == status
    assert client.simulate_get(f'/api/entries/{former[0]}').json['activity_type'] is None
