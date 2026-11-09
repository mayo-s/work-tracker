import datetime as dt

import falcon
import pytest

from src.models.entries import Entry
from src.modules.storage.catalog import ServiceRepository
from src.modules.storage.entries import EntryRepository
from src.tests.ids import CODING
from src.tests.users import USER


@pytest.fixture
def his(database):
    with database.transaction() as conn:
        return next(service.id for service in ServiceRepository(conn, USER).all() if service.short_name == 'HiS')


def add_entry(client, key, duration='1:00', date='2026-03-02'):
    body = {'activity_type_id': CODING, 'date': date, 'duration': duration, 'ticket_key': key}
    return client.simulate_post('/api/entries', json=body).json


def get_review(client):
    result = client.simulate_get('/api/review')
    assert result.status == falcon.HTTP_200
    return result.json


def test_empty_review(client):
    assert get_review(client) == {
        'counts': {'tickets_without_service': 0, 'entries': 0},
        'tickets_without_service': [],
        'entries': [],
    }


def test_tickets_without_service_leave_once_assigned(client, his):
    add_entry(client, 'AGA-39')
    add_entry(client, 'AGA-39', date='2026-03-03')
    add_entry(client, 'TNG-5214')
    assert [(ticket['key'], ticket['entries']) for ticket in get_review(client)['tickets_without_service']] == [
        ('AGA-39', 2), ('TNG-5214', 1)]
    client.simulate_put('/api/tickets/AGA-39', json={'service_id': his})
    assert [ticket['key'] for ticket in get_review(client)['tickets_without_service']] == ['TNG-5214']


def test_tickets_without_entries_are_not_listed(client, database):
    with database.transaction() as conn:
        conn.execute("INSERT INTO tickets (user_id, key) VALUES (?, 'TNG-4138')", (USER,))
    assert get_review(client)['tickets_without_service'] == []


def test_entry_with_zero_duration_leaves_once_fixed(client):
    entry = add_entry(client, 'KP-2045', duration='0:00')
    [item] = get_review(client)['entries']
    assert (item['entry']['id'], item['reasons']) == (entry['id'], ['zero_duration'])
    body = {'activity_type_id': CODING, 'date': '2026-03-02', 'duration': '0:45', 'ticket_key': 'KP-2045'}
    client.simulate_put(f'/api/entries/{entry["id"]}', json=body)
    assert get_review(client)['entries'] == []


def test_entry_without_ticket(client, database):
    with database.transaction() as conn:
        review_entry = Entry(date=dt.date(2025, 11, 26), activity_type_id=CODING, duration=360, description='PR reviews')
        EntryRepository(conn, USER).create(review_entry)
    [item] = get_review(client)['entries']
    assert (item['entry']['description'], item['reasons']) == ('PR reviews', ['no_ticket'])


def test_entry_without_activity_type(client, database):
    with database.transaction() as conn:
        EntryRepository(conn, USER).create(Entry(date=dt.date(2025, 11, 26), ticket_key='TNG-1', duration=60))
    [item] = get_review(client)['entries']
    assert item['reasons'] == ['no_activity_type']
    assert client.simulate_get('/api/review/counts').json == {'tickets_without_service': 1, 'entries': 1}
