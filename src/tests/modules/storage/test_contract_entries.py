"""Task entries with their history: the same behaviour on SQLite and on DynamoDB (moto)."""

import datetime as dt

import pytest

from src.models.base import new_id
from src.models.entries import Entry
from src.models.history import EntryChange, HistoryAction
from src.modules.storage.errors import ConflictError, NotFoundError

MONDAY = dt.date(2026, 10, 26)
NOW = dt.datetime(2026, 10, 28, 14, 5)


@pytest.fixture
def entries(per_call, klara_id):
    return per_call(lambda store: store.entries(klara_id, clock=lambda: NOW))


@pytest.fixture
def days(per_call, klara_id):
    return per_call(lambda store: store.days(klara_id))


@pytest.fixture
def tickets(per_call, klara_id):
    return per_call(lambda store: store.tickets(klara_id))


@pytest.fixture
def ticket_entry(coding_id):
    return Entry(date=MONDAY, activity_type_id=coding_id, ticket_key='ENGINE-597', duration=90,
                 description='europace permissions')


@pytest.fixture
def activity_entry(activity_type_ids):
    return Entry(date=MONDAY, activity_type_id=activity_type_ids['Planning'], duration=120, description='GCC Tactical')


def test_create_and_get(entries, tickets, ticket_entry, activity_entry):
    without_ticket = Entry(date=MONDAY, activity_type_id=ticket_entry.activity_type_id, duration=360,
                           description='PR reviews zipkin lib')
    former = Entry(date=MONDAY, ticket_key='TNG-1', duration=60, description='investigation')  # no activity type yet
    for entry in (ticket_entry, without_ticket, activity_entry, former):
        created = entries.create(entry)
        assert entries.get(created.id) == created
    assert [ticket.key for ticket in tickets.all()] == ['ENGINE-597', 'TNG-1']  # an entry's ticket is created with it


def test_create_with_unknown_activity_type(entries):
    unknown = Entry(date=MONDAY, activity_type_id=new_id(), duration=60)
    with pytest.raises(ConflictError):
        entries.create(unknown)


def test_create_records_initial_values(entries, ticket_entry):
    created = entries.create(ticket_entry)
    [change] = entries.history(created.id)
    assert change.action is HistoryAction.CREATED
    assert change.changed_at == NOW
    assert change.changes == {
        'date': (None, '2026-10-26'),
        'activity_type_id': (None, ticket_entry.activity_type_id),
        'ticket_key': (None, 'ENGINE-597'),
        'duration': (None, 90),
        'description': (None, 'europace permissions'),
    }


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


def test_update_without_changes_records_nothing(entries, ticket_entry):
    created = entries.create(ticket_entry)
    entries.update(created)
    assert len(entries.history(created.id)) == 1


def test_missing_entry(entries, ticket_entry):
    with pytest.raises(NotFoundError):
        entries.get(404)
    with pytest.raises(NotFoundError):
        entries.update(ticket_entry.model_copy(update={'id': 404}))
    with pytest.raises(NotFoundError):
        entries.delete(404)


def test_delete_removes_entry_and_keeps_history_with_last_values(entries, activity_entry):
    created = entries.create(activity_entry)
    entries.delete(created.id)
    assert entries.between(MONDAY, MONDAY) == []
    actions = [change.action for change in entries.history(created.id)]
    assert actions == [HistoryAction.CREATED, HistoryAction.DELETED]
    assert entries.history(created.id)[-1].changes['description'] == ('GCC Tactical', None)


def test_all_history_includes_deleted_entries_in_written_order(entries, ticket_entry, activity_entry):
    deleted, kept = entries.create(activity_entry), entries.create(ticket_entry)
    entries.delete(deleted.id)
    lines = [(change.entry_id, change.action) for change in entries.all_history()]
    assert lines == [(deleted.id, HistoryAction.CREATED), (kept.id, HistoryAction.CREATED),
                     (deleted.id, HistoryAction.DELETED)]


def test_restore_writes_no_history_line_and_restored_history_keeps_its_time(entries, ticket_entry):
    restored = entries.restore(ticket_entry)
    assert entries.get(restored.id) == restored
    assert entries.history(restored.id) == []
    change = EntryChange(entry_id=restored.id, changed_at=dt.datetime(2025, 3, 4, 8, 15), action=HistoryAction.IMPORTED,
                         changes={'duration': (None, 90)}, detail='3,0 ENGINE-597')
    entries.restore_history(change)
    assert entries.history(restored.id)[0].model_copy(update={'id': None}) == change


def test_reserved_ids_are_never_given_to_entries(entries, ticket_entry):
    reserved = entries.reserve_id()
    with pytest.raises(NotFoundError):
        entries.get(reserved)
    assert entries.create(ticket_entry).id > reserved


def test_changed_marks_entries_changed_after_creation_or_import(entries, ticket_entry, activity_entry):
    unchanged = entries.create(ticket_entry)
    imported = entries.restore(activity_entry)  # by the former spreadsheet import: its history starts with `imported`
    entries.add_history(imported.id, HistoryAction.IMPORTED, {'duration': (None, 120)}, '2,0 GCC Tactical')
    changed = entries.create(ticket_entry)
    entries.update(changed.model_copy(update={'description': 'europace roles'}))
    assert entries.changed([unchanged.id, imported.id, changed.id]) == {changed.id}
    assert entries.changed([]) == set()


def test_entries_for_review(entries, ticket_entry, activity_entry):
    entries.create(ticket_entry)
    entries.create(activity_entry)
    zero = entries.create(ticket_entry.model_copy(update={'duration': 0, 'date': MONDAY + dt.timedelta(days=1)}))
    sunday = MONDAY - dt.timedelta(days=1)
    no_ticket = entries.create(ticket_entry.model_copy(update={'ticket_key': None, 'date': sunday}))  # Coding needs one
    no_type = entries.create(Entry(date=sunday, ticket_key='TNG-1', duration=60))
    assert [entry.id for entry in entries.for_review()] == [no_ticket.id, no_type.id, zero.id]


def test_update_to_new_ticket_creates_ticket(entries, tickets, ticket_entry):
    created = entries.create(ticket_entry)
    entries.update(created.model_copy(update={'ticket_key': 'ENGINE-598'}))
    assert tickets.get('ENGINE-598') is not None
    assert entries.history(created.id)[-1].changes == {'ticket_key': ('ENGINE-597', 'ENGINE-598')}
