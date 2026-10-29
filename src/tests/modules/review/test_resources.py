import datetime as dt

import falcon
import pytest

from src.models.entries import TicketEntry
from src.models.history import HistoryAction
from src.models.review import FlagReason
from src.modules.storage.catalog import ServiceRepository
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository


@pytest.fixture
def his(database):
    with database.transaction() as conn:
        return next(service.id for service in ServiceRepository(conn).all() if service.short_name == 'HiS')


def add_entry(client, key, duration='1:00', date='2026-03-02'):
    body = {'kind': 'ticket', 'date': date, 'duration': duration, 'ticket_key': key}
    return client.simulate_post('/api/entries', json=body).json


def get_review(client):
    result = client.simulate_get('/api/review')
    assert result.status == falcon.HTTP_200
    return result.json


def test_empty_review(client):
    assert get_review(client) == {
        'counts': {'tickets_without_service': 0, 'entries': 0, 'days': 0},
        'tickets_without_service': [],
        'entries': [],
        'days': [],
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
        conn.execute("INSERT INTO tickets (key) VALUES ('TNG-4138')")
    assert get_review(client)['tickets_without_service'] == []


def test_entry_with_zero_duration_leaves_once_fixed(client):
    entry = add_entry(client, 'KP-2045', duration='0:00')
    [item] = get_review(client)['entries']
    assert (item['entry']['id'], item['reasons']) == (entry['id'], ['zero_duration'])
    body = {'kind': 'ticket', 'date': '2026-03-02', 'duration': '0:45', 'ticket_key': 'KP-2045'}
    client.simulate_put(f'/api/entries/{entry["id"]}', json=body)
    assert get_review(client)['entries'] == []


def test_entry_without_ticket(client, database):
    with database.transaction() as conn:
        review_entry = TicketEntry(date=dt.date(2025, 11, 26), duration=360, description='PR reviews', coding=True)
        EntryRepository(conn).create(review_entry)
    [item] = get_review(client)['entries']
    assert (item['entry']['description'], item['reasons']) == ('PR reviews', ['no_ticket'])


def test_flagged_entry_leaves_once_flag_is_cleared(client, database):
    entry = add_entry(client, 'TNG-4347', duration='0:00')
    with database.transaction() as conn:
        flag = EntryRepository(conn).add_flag(entry['id'], FlagReason.UNCERTAIN_TICKET, '#4347 aka #1482')
    [item] = get_review(client)['entries']
    assert item['reasons'] == ['uncertain_ticket', 'zero_duration']
    assert client.simulate_delete(f'/api/review/flags/{flag.id}').status == falcon.HTTP_204
    [item] = get_review(client)['entries']
    assert item['reasons'] == ['zero_duration']


def test_flagged_day_leaves_once_flag_is_cleared(client, database):
    client.simulate_put('/api/days/2025-12-06', json={'start': '08:00', 'end': '11:30', 'break_time': '0:00'})
    with database.transaction() as conn:
        flag = DayRepository(conn).add_flag(dt.date(2025, 12, 6), FlagReason.WEEKEND_HOURS, '3,5 ABREISE Lübeck')
    [day] = get_review(client)['days']
    assert (day['date'], day['worked'], day['flags'][0]['detail']) == ('2025-12-06', '3:30', '3,5 ABREISE Lübeck')
    assert get_review(client)['counts']['days'] == 1
    assert client.simulate_delete(f'/api/review/flags/{flag.id}').status == falcon.HTTP_204
    assert get_review(client)['days'] == []


def test_flagged_day_without_record(client, database):
    with database.transaction() as conn:
        DayRepository(conn).add_flag(dt.date(2024, 11, 9), FlagReason.WEEKEND_HOURS, '5,0 Secretary')
    [day] = get_review(client)['days']
    assert (day['date'], day['recorded']) == ('2024-11-09', False)


def test_clear_unknown_flag(client):
    assert client.simulate_delete('/api/review/flags/404').status == falcon.HTTP_404


def test_entry_split_on_import_is_shown(client, database):
    line = '6,0 #4138, #4139 create meeting service'
    with database.transaction() as conn:
        repository = EntryRepository(conn)
        for key in ('TNG-4138', 'TNG-4139'):
            created = repository.create(TicketEntry(date=dt.date(2024, 6, 10), ticket_key=key, duration=180),
                                        HistoryAction.IMPORTED, line)
            repository.add_flag(created.id, FlagReason.UNCERTAIN_TICKET, line)
    items = get_review(client)['entries']
    assert [item['split_on_import'] for item in items] == [
        [{'ticket_key': 'TNG-4138', 'duration': '3:00'}, {'ticket_key': 'TNG-4139', 'duration': '3:00'}]] * 2


def test_entry_imported_alone_has_no_split(client, database):
    with database.transaction() as conn:
        repository = EntryRepository(conn)
        created = repository.create(TicketEntry(date=dt.date(2024, 6, 19), ticket_key='TNG-4156', duration=60),
                                    HistoryAction.IMPORTED, '1,0 #4156')
        repository.add_flag(created.id, FlagReason.UNCERTAIN_TICKET, '1,0 #4156')
    assert get_review(client)['entries'][0]['split_on_import'] == []
