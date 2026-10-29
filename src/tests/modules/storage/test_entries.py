import datetime as dt

import pytest

from src.models.entries import ActivityEntry, TicketEntry
from src.models.history import HistoryAction
from src.models.review import FlagReason
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.tickets import TicketRepository
from src.tests.users import USER

MONDAY = dt.date(2026, 10, 26)
NOW = dt.datetime(2026, 10, 28, 14, 5)


@pytest.fixture
def entries(conn):
    return EntryRepository(conn, USER,  clock=lambda: NOW)


@pytest.fixture
def ticket_entry():
    return TicketEntry(date=MONDAY, ticket_key='ENGINE-597', duration=90, description='europace permissions', coding=True)


@pytest.fixture
def activity_entry():
    return ActivityEntry(date=MONDAY, activity_type_id=1, duration=120, note='GCC Tactical')


def test_create_and_get_ticket_entry(entries, ticket_entry):
    created = entries.create(ticket_entry)
    assert created.id is not None
    assert entries.get(created.id) == created


def test_create_ticket_entry_creates_ticket(entries, conn, ticket_entry):
    entries.create(ticket_entry)
    assert TicketRepository(conn, USER).get('ENGINE-597') is not None


def test_create_ticket_entry_without_ticket(entries):
    created = entries.create(TicketEntry(date=MONDAY, duration=360, description='PR reviews zipkin lib', coding=True))
    assert entries.get(created.id).ticket_key is None


def test_create_and_get_activity_entry(entries, activity_entry):
    created = entries.create(activity_entry)
    assert entries.get(created.id) == created


def test_create_with_unknown_activity_type(entries):
    unknown = ActivityEntry(date=MONDAY, activity_type_id=404, duration=60)
    with pytest.raises(ConflictError):
        entries.create(unknown)


def test_create_records_initial_values(entries, ticket_entry):
    created = entries.create(ticket_entry)
    [change] = entries.history(created.id)
    assert change.action is HistoryAction.CREATED
    assert change.changed_at == NOW
    assert change.changes == {
        'date': (None, '2026-10-26'),
        'ticket_key': (None, 'ENGINE-597'),
        'duration': (None, 90),
        'description': (None, 'europace permissions'),
        'coding': (None, True),
    }


def test_import_records_original_line(entries):
    entry = TicketEntry(date=dt.date(2026, 2, 17), ticket_key='TNG-5213', duration=90)
    created = entries.create(entry, HistoryAction.IMPORTED, '3,0 TNG-5213, TNG-5214')
    [change] = entries.history(created.id)
    assert change.action is HistoryAction.IMPORTED
    assert change.detail == '3,0 TNG-5213, TNG-5214'


def test_get_missing_entry(entries):
    with pytest.raises(NotFoundError):
        entries.get(404)


def test_between_by_date_and_creation_order(entries, ticket_entry, activity_entry):
    later = entries.create(ticket_entry.model_copy(update={'date': MONDAY + dt.timedelta(days=1)}))
    first = entries.create(ticket_entry)
    second = entries.create(activity_entry)
    entries.create(ticket_entry.model_copy(update={'date': MONDAY + dt.timedelta(days=7)}))
    assert entries.between(MONDAY, MONDAY + dt.timedelta(days=6)) == [first, second, later]


def test_update_records_only_changed_fields(entries, ticket_entry):
    created = entries.create(ticket_entry)
    entries.update(created.model_copy(update={'duration': 120, 'description': 'europace permissions, PR'}))
    change = entries.history(created.id)[-1]
    assert change.action is HistoryAction.UPDATED
    assert change.changes == {
        'duration': (90, 120),
        'description': ('europace permissions', 'europace permissions, PR'),
    }
    assert entries.get(created.id).duration == 120


def test_update_to_new_ticket_creates_ticket(entries, conn, ticket_entry):
    created = entries.create(ticket_entry)
    entries.update(created.model_copy(update={'ticket_key': 'ENGINE-598'}))
    assert TicketRepository(conn, USER).get('ENGINE-598') is not None
    assert entries.history(created.id)[-1].changes == {'ticket_key': ('ENGINE-597', 'ENGINE-598')}


def test_update_without_changes_records_nothing(entries, ticket_entry):
    created = entries.create(ticket_entry)
    entries.update(created)
    assert len(entries.history(created.id)) == 1


def test_update_cannot_change_kind(entries, ticket_entry):
    created = entries.create(ticket_entry)
    activity = ActivityEntry(id=created.id, date=MONDAY, activity_type_id=1, duration=90)
    with pytest.raises(ConflictError):
        entries.update(activity)


def test_update_missing_entry(entries, ticket_entry):
    missing = ticket_entry.model_copy(update={'id': 404})
    with pytest.raises(NotFoundError):
        entries.update(missing)


def test_delete_keeps_history_with_last_values(entries, activity_entry):
    created = entries.create(activity_entry)
    entries.delete(created.id)
    actions = [change.action for change in entries.history(created.id)]
    assert actions == [HistoryAction.CREATED, HistoryAction.DELETED]
    assert entries.history(created.id)[-1].changes['note'] == ('GCC Tactical', None)


def test_delete_removes_entry_and_its_flags(entries, ticket_entry):
    created = entries.create(ticket_entry)
    entries.add_flag(created.id, FlagReason.UNCERTAIN_TICKET)
    entries.delete(created.id)
    assert entries.between(MONDAY, MONDAY) == []
    assert entries.flags_of(created.id) == []


def test_delete_missing_entry(entries):
    with pytest.raises(NotFoundError):
        entries.delete(404)


def test_changed_marks_entries_changed_after_creation(entries, ticket_entry, activity_entry):
    unchanged = entries.create(ticket_entry)
    imported = entries.create(activity_entry, HistoryAction.IMPORTED)
    changed = entries.create(ticket_entry)
    entries.update(changed.model_copy(update={'coding': False}))
    assert entries.changed([unchanged.id, imported.id, changed.id]) == {changed.id}
    assert entries.changed([]) == set()


def test_entry_flags(entries, conn, ticket_entry):
    created = entries.create(ticket_entry)
    flag = entries.add_flag(created.id, FlagReason.UNCERTAIN_TICKET, '#4347 aka #1482')
    DayRepository(conn, USER).add_flag(MONDAY, FlagReason.WEEKEND_HOURS)
    assert entries.flags_of(created.id) == [flag]
    assert entries.entry_flags() == [flag]


def test_flag_on_missing_entry(entries):
    with pytest.raises(ConflictError):
        entries.add_flag(404, FlagReason.UNCERTAIN_TICKET)


def test_clear_entry_flag(entries, ticket_entry):
    created = entries.create(ticket_entry)
    flag = entries.add_flag(created.id, FlagReason.UNCERTAIN_TICKET)
    entries.clear_flag(flag.id)
    assert entries.flags_of(created.id) == []


def test_clear_missing_entry_flag(entries, conn):
    day_flag = DayRepository(conn, USER).add_flag(MONDAY, FlagReason.WEEKEND_HOURS)
    with pytest.raises(NotFoundError):
        entries.clear_flag(day_flag.id)


def test_entries_for_review(entries, ticket_entry, activity_entry):
    entries.create(ticket_entry)
    entries.create(activity_entry)
    zero = entries.create(ticket_entry.model_copy(update={'duration': 0, 'date': MONDAY + dt.timedelta(days=1)}))
    no_ticket = entries.create(TicketEntry(date=MONDAY - dt.timedelta(days=1), duration=360, coding=True))
    flagged = entries.create(activity_entry)
    entries.add_flag(flagged.id, FlagReason.UNCERTAIN_TICKET)
    assert [entry.id for entry in entries.for_review()] == [no_ticket.id, flagged.id, zero.id]


def test_split_entry_evenly_with_history(entries, conn):
    entry = entries.create(
        TicketEntry(date=MONDAY, ticket_key='TNG-4347', duration=360, description='adapt tests', coding=True)
    )
    first, second = entries.split(entry.id, ['tng-4347', 'KP-1482'])
    assert (first.id, first.ticket_key, first.duration) == (entry.id, 'TNG-4347', 180)
    assert (second.ticket_key, second.duration, second.description, second.coding) == ('KP-1482', 180, 'adapt tests', True)
    assert TicketRepository(conn, USER).get('KP-1482') is not None
    original = entries.history(entry.id)[-1]
    assert (original.action, original.changes, original.detail) == (
        HistoryAction.SPLIT, {'duration': (360, 180)}, 'Split into TNG-4347, KP-1482')
    [created] = entries.history(second.id)
    assert (created.action, created.detail) == (HistoryAction.SPLIT, f'Split from entry {entry.id}')


def test_split_into_quarter_hours(entries):
    entry = entries.create(TicketEntry(date=MONDAY, ticket_key='TNG-2035', duration=90))
    split = entries.split(entry.id, ['KP-2035', 'KP-2044', 'KP-2045', 'KP-2053'])
    expected = [('KP-2035', 30), ('KP-2044', 30), ('KP-2045', 15), ('KP-2053', 15)]
    assert [(item.ticket_key, item.duration) for item in split] == expected


@pytest.mark.parametrize('keys', [['TNG-4347'], ['TNG-4347', 'tng-4347']])
def test_split_needs_two_different_tickets(entries, keys):
    entry = entries.create(TicketEntry(date=MONDAY, ticket_key='TNG-4347', duration=60))
    with pytest.raises(ConflictError):
        entries.split(entry.id, keys)


def test_split_activity_entry_is_refused(entries, activity_entry):
    entry = entries.create(activity_entry)
    with pytest.raises(ConflictError):
        entries.split(entry.id, ['TNG-1', 'TNG-2'])


def test_entries_imported_together(entries):
    line = '6,0 #4138, #4139 create meeting service'
    first = entries.create(TicketEntry(date=MONDAY, ticket_key='TNG-4138', duration=180), HistoryAction.IMPORTED, line)
    second = entries.create(TicketEntry(date=MONDAY, ticket_key='TNG-4139', duration=180), HistoryAction.IMPORTED, line)
    next_day = TicketEntry(date=MONDAY + dt.timedelta(days=1), ticket_key='TNG-4138', duration=60)
    entries.create(next_day, HistoryAction.IMPORTED, line)
    alone = entries.create(TicketEntry(date=MONDAY, ticket_key='TNG-4145', duration=60), HistoryAction.IMPORTED, '1,0 #4145')
    created = entries.create(TicketEntry(date=MONDAY, ticket_key='TNG-5882', duration=60))
    assert [entry.id for entry in entries.imported_together(first.id)] == [first.id, second.id]
    assert [entry.id for entry in entries.imported_together(alone.id)] == [alone.id]
    assert entries.imported_together(created.id) == []
