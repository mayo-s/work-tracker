"""Renaming and merging tickets: the same behaviour on SQLite and on DynamoDB (moto)."""

import datetime as dt

import pytest
from pydantic import ValidationError

from src.models.entries import Entry
from src.models.history import HistoryAction
from src.modules.storage.errors import ConflictError, NotFoundError

NOW = dt.datetime(2026, 10, 28, 15, 30)


@pytest.fixture
def entries(per_call, klara_id):
    return per_call(lambda store: store.entries(klara_id, clock=lambda: NOW))


@pytest.fixture
def tickets(per_call, klara_id):
    return per_call(lambda store: store.tickets(klara_id))


@pytest.fixture
def rename(storage, klara_id):
    def rename(old_key, new_key):
        with storage.transaction() as store:
            return store.rename_ticket(klara_id, old_key, new_key, clock=lambda: NOW)
    return rename


def ticket_entry(key, day=1):
    return Entry(date=dt.date(2026, 3, day), ticket_key=key, duration=60, description=f'work on {key}')


def test_rename_moves_the_entries_with_a_history_line_each(rename, entries, tickets, service_ids, activity_type_ids):
    first, second = entries.create(ticket_entry('TNG-2035')), entries.create(ticket_entry('TNG-2035', 2))
    other = entries.create(ticket_entry('TNG-5214'))
    activity = entries.create(Entry(date=dt.date(2026, 3, 1), activity_type_id=activity_type_ids['Meeting'], duration=60))
    tickets.set_service('TNG-2035', service_ids['ImmoDrop'])
    result = rename(' tng-2035', 'kp-2035 ')
    assert (result.action, result.moved, result.ticket.key) == (HistoryAction.RENAMED, 2, 'KP-2035')
    assert result.ticket.service_id == service_ids['ImmoDrop']
    assert tickets.get('TNG-2035') is None
    assert [entries.get(entry.id) for entry in (first, second)] == [
        entry.model_copy(update={'ticket_key': 'KP-2035'}) for entry in (first, second)]
    change = entries.history(first.id)[-1]
    assert (change.action, change.changed_at, change.changes) == (
        HistoryAction.RENAMED, NOW, {'ticket_key': ('TNG-2035', 'KP-2035')})
    assert entries.changed([first.id]) == {first.id}
    assert (entries.get(other.id), entries.get(activity.id), len(entries.history(other.id))) == (other, activity, 1)


def test_rename_ticket_without_entries(rename, tickets):
    tickets.ensure('TNG-4138')
    result = rename('TNG-4138', 'KP-4138')
    assert (result.ticket.key, result.moved) == ('KP-4138', 0)


def test_merge_into_existing_ticket_keeps_its_service(rename, entries, tickets, service_ids):
    moved = entries.create(ticket_entry('TNG-4347'))
    existing = entries.create(ticket_entry('KP-1482', 2))
    tickets.set_service('TNG-4347', service_ids['MSB'])
    tickets.set_service('KP-1482', service_ids['HiS'])
    result = rename('TNG-4347', 'KP-1482')
    assert result.action is HistoryAction.MERGED
    assert result.moved == 1
    assert result.ticket.service_id == service_ids['HiS']
    assert tickets.get('TNG-4347') is None
    assert entries.history(moved.id)[-1].action is HistoryAction.MERGED
    assert len(entries.history(existing.id)) == 1


def test_merge_takes_service_when_existing_ticket_has_none(rename, entries, tickets, service_ids):
    entries.create(ticket_entry('TNG-4347'))
    tickets.ensure('KP-1482')
    tickets.set_service('TNG-4347', service_ids['MSB'])
    assert rename('TNG-4347', 'KP-1482').ticket.service_id == service_ids['MSB']


def test_rename_unknown_ticket(rename):
    with pytest.raises(NotFoundError):
        rename('TNG-404', 'KP-404')


def test_rename_to_itself(rename, tickets):
    tickets.ensure('KP-2035')
    with pytest.raises(ConflictError):
        rename('KP-2035', 'kp-2035')


def test_rename_to_invalid_key(rename, tickets):
    tickets.ensure('TNG-2035')
    with pytest.raises(ValidationError):
        rename('TNG-2035', 'TNG-2035ff')


def test_renaming_a_ticket_with_more_entries_than_one_transaction_holds(rename, entries, tickets):
    for day in range(1, 41):  # 40 entries, three items each: more than 100 items to change
        entries.create(ticket_entry('TNG-2035', day % 28 + 1))
    assert rename('TNG-2035', 'KP-2035').moved == 40
    assert tickets.get('TNG-2035') is None
    assert {entry.ticket_key for entry in entries.between(dt.date(2026, 3, 1), dt.date(2026, 3, 31))} == {'KP-2035'}
