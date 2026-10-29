import datetime as dt

import pytest
from pydantic import ValidationError

from src.models.entries import ActivityEntry, TicketEntry
from src.models.history import HistoryAction
from src.modules.storage.catalog import ServiceRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.renames import rename_ticket
from src.modules.storage.tickets import TicketRepository
from src.tests.users import USER

NOW = dt.datetime(2026, 10, 28, 15, 30)


@pytest.fixture
def entries(conn):
    return EntryRepository(conn, USER,  clock=lambda: NOW)


@pytest.fixture
def tickets(conn):
    return TicketRepository(conn, USER)


@pytest.fixture
def service_ids(conn):
    return {service.short_name: service.id for service in ServiceRepository(conn, USER).all()}


def ticket_entry(key, day=1):
    return TicketEntry(date=dt.date(2026, 3, day), ticket_key=key, duration=60, description=f'work on {key}')


def rename(conn, old_key, new_key):
    return rename_ticket(conn, USER, old_key, new_key, clock=lambda: NOW)


def test_rename_moves_entries_and_keeps_service(conn, entries, tickets, service_ids):
    first, second = entries.create(ticket_entry('TNG-2035')), entries.create(ticket_entry('TNG-2035', 2))
    tickets.set_service('TNG-2035', service_ids['ImmoDrop'])
    result = rename(conn, 'TNG-2035', 'KP-2035')
    assert result.action is HistoryAction.RENAMED
    assert result.moved == 2
    assert result.ticket.service_id == service_ids['ImmoDrop']
    assert tickets.get('TNG-2035') is None
    assert [entries.get(entry.id).ticket_key for entry in (first, second)] == ['KP-2035', 'KP-2035']


def test_rename_writes_history_line_per_entry(conn, entries):
    created = entries.create(ticket_entry('TNG-2035'))
    rename(conn, 'TNG-2035', 'KP-2035')
    change = entries.history(created.id)[-1]
    assert change.action is HistoryAction.RENAMED
    assert change.changed_at == NOW
    assert change.changes == {'ticket_key': ('TNG-2035', 'KP-2035')}
    assert entries.changed([created.id]) == {created.id}


def test_rename_keeps_other_fields(conn, entries):
    created = entries.create(ticket_entry('TNG-2035'))
    rename(conn, 'TNG-2035', 'KP-2035')
    assert entries.get(created.id) == created.model_copy(update={'ticket_key': 'KP-2035'})


def test_rename_ticket_without_entries(conn, tickets):
    tickets.ensure('TNG-4138')
    result = rename(conn, 'TNG-4138', 'KP-4138')
    assert (result.ticket.key, result.moved) == ('KP-4138', 0)


def test_rename_normalizes_keys(conn, entries):
    entries.create(ticket_entry('TNG-2035'))
    assert rename(conn, ' tng-2035', 'kp-2035 ').ticket.key == 'KP-2035'


def test_rename_leaves_other_entries_untouched(conn, entries):
    other = entries.create(ticket_entry('TNG-5214'))
    activity = entries.create(ActivityEntry(date=dt.date(2026, 3, 1), activity_type_id=1, duration=60))
    entries.create(ticket_entry('TNG-2035'))
    rename(conn, 'TNG-2035', 'KP-2035')
    assert entries.get(other.id) == other
    assert entries.get(activity.id) == activity
    assert len(entries.history(other.id)) == 1


def test_merge_into_existing_ticket_keeps_its_service(conn, entries, tickets, service_ids):
    moved = entries.create(ticket_entry('TNG-4347'))
    existing = entries.create(ticket_entry('KP-1482', 2))
    tickets.set_service('TNG-4347', service_ids['MSB'])
    tickets.set_service('KP-1482', service_ids['HiS'])
    result = rename(conn, 'TNG-4347', 'KP-1482')
    assert result.action is HistoryAction.MERGED
    assert result.moved == 1
    assert result.ticket.service_id == service_ids['HiS']
    assert tickets.get('TNG-4347') is None
    assert entries.history(moved.id)[-1].action is HistoryAction.MERGED
    assert len(entries.history(existing.id)) == 1


def test_merge_takes_service_when_existing_ticket_has_none(conn, entries, tickets, service_ids):
    entries.create(ticket_entry('TNG-4347'))
    tickets.ensure('KP-1482')
    tickets.set_service('TNG-4347', service_ids['MSB'])
    assert rename(conn, 'TNG-4347', 'KP-1482').ticket.service_id == service_ids['MSB']


def test_rename_unknown_ticket(conn):
    with pytest.raises(NotFoundError):
        rename(conn, 'TNG-404', 'KP-404')


def test_rename_to_itself(conn, tickets):
    tickets.ensure('KP-2035')
    with pytest.raises(ConflictError):
        rename(conn, 'KP-2035', 'kp-2035')


def test_rename_to_invalid_key(conn, tickets):
    tickets.ensure('TNG-2035')
    with pytest.raises(ValidationError):
        rename(conn, 'TNG-2035', 'TNG-2035ff')
