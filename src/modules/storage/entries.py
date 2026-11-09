"""Task entries with their change history."""

import datetime as dt
import json
import sqlite3
from collections.abc import Callable, Iterable

from pydantic import JsonValue

from src.lib.durations import MINUTES_PER_DAY, format_clock, format_duration
from src.models.base import new_id
from src.models.entries import Entry
from src.models.history import EntryChange, HistoryAction
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.store import Changes
from src.modules.storage.tickets import TicketRepository

_ENTRY_COLUMNS = 'id, date, activity_type_id, ticket_key, duration, description'
_HISTORY_COLUMNS = 'id, entry_id, changed_at, action, changes, detail'


def history_time() -> dt.datetime:
    """The time of a history line, to the second."""
    return dt.datetime.now().replace(microsecond=0)


def _to_entry(row: sqlite3.Row) -> Entry:
    return Entry(**dict(row))


def _to_values(entry: Entry) -> tuple:
    """Column values for date, activity_type_id, ticket_key, duration, description."""
    return entry.date.isoformat(), entry.activity_type_id, entry.ticket_key, entry.duration, entry.description


def entry_fields(entry: Entry) -> dict[str, JsonValue]:
    """The fields a history line records changes of."""
    return entry.model_dump(mode='json', exclude={'id'})


def field_changes(old: dict[str, JsonValue], new: dict[str, JsonValue]) -> Changes:
    """Each changed field as (old, new); a new entry has no old values, a deleted one no new ones."""
    return {field: (old.get(field), new.get(field)) for field in old | new if old.get(field) != new.get(field)}


def _to_change(row: sqlite3.Row) -> EntryChange:
    return EntryChange(**{**dict(row), 'changes': json.loads(row['changes'])})


class EntryRules:
    """The rules of entries on every backend: creating, changing and deleting write the history. A backend's
    repository stores them: `get`, `restore`, `restore_history`, `_check_references`, `_replace` (an entry in place of
    its old version) and `_remove` (an entry)."""

    _clock: Callable[[], dt.datetime]

    def create(self, entry: Entry) -> Entry:
        """Store a new entry; its ticket is created if needed."""
        created = self.restore(entry)
        self.add_history(created.id, HistoryAction.CREATED, field_changes({}, entry_fields(created)))
        return created

    def update(self, entry: Entry, action: HistoryAction = HistoryAction.UPDATED) -> Entry:
        """Replace an entry; only changed fields are recorded (`action`: e.g. `renamed` when its ticket was)."""
        old = self.get(entry.id)
        if changes := field_changes(entry_fields(old), entry_fields(entry)):
            self._check_references(entry)
            self._replace(old, entry)
            self.add_history(entry.id, action, changes)
        return entry

    def delete(self, entry_id: str) -> None:
        """Delete an entry; its history is kept."""
        old = self.get(entry_id)
        self._remove(old)
        self.add_history(entry_id, HistoryAction.DELETED, field_changes(entry_fields(old), {}))

    def reserve_id(self) -> str:
        """An id no entry will get, for an entry known only from its history (deleted before an export)."""
        return new_id()

    def add_history(self, entry_id: str, action: HistoryAction, changes: Changes, detail: str = '') -> EntryChange:
        return self.restore_history(
            EntryChange(entry_id=entry_id, changed_at=self._clock(), action=action, changes=changes, detail=detail))


class EntryRepository(EntryRules):
    """Task entries of one user; every change is written to the entry's history.

    Works within the transaction of the given connection. `clock` provides the history timestamps.
    """

    def __init__(self, conn: sqlite3.Connection, user_id: str, clock: Callable[[], dt.datetime] | None = None) -> None:
        self._conn = conn
        self._user = user_id
        self._clock = clock or history_time
        self._tickets = TicketRepository(conn, user_id)

    def get(self, entry_id: str) -> Entry:
        row = self._conn.execute(f'SELECT {_ENTRY_COLUMNS} FROM entries WHERE id = ? AND user_id = ?',
                                 (entry_id, self._user)).fetchone()
        if row is None:
            raise NotFoundError(f'No entry with id {entry_id}')
        return _to_entry(row)

    def between(self, start: dt.date, end: dt.date) -> list[Entry]:
        """Entries from start to end (inclusive), by date and in the order they were created."""
        rows = self._conn.execute(
            f'SELECT {_ENTRY_COLUMNS} FROM entries WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date, id',
            (self._user, start.isoformat(), end.isoformat()),
        )
        return [_to_entry(row) for row in rows]

    def for_review(self) -> list[Entry]:
        """Entries with 0:00, without activity type or without the ticket their activity type requires, by date."""
        rows = self._conn.execute(
            f'SELECT {_ENTRY_COLUMNS} FROM entries '
            'WHERE user_id = ? AND (duration = 0 OR activity_type_id IS NULL OR (ticket_key IS NULL AND activity_type_id IN '
            '(SELECT id FROM activity_types WHERE ticket_required))) ORDER BY date, id',
            (self._user,),
        )
        return [_to_entry(row) for row in rows]

    def restore(self, entry: Entry) -> Entry:
        """Store an entry without a history line (its history comes along, e.g. from an export file); its ticket is
        created if needed."""
        self._check_references(entry)
        restored = entry.model_copy(update={'id': new_id()})
        self._write(
            'INSERT INTO entries (id, user_id, date, activity_type_id, ticket_key, duration, description) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (restored.id, self._user, *_to_values(entry)),
        )
        return restored

    def restore_history(self, change: EntryChange) -> EntryChange:
        """Store a history line as it was, with its own time."""
        stored = change.model_copy(update={'id': new_id()})
        self._conn.execute(
            'INSERT INTO entry_history (id, user_id, entry_id, changed_at, action, changes, detail)'
            ' VALUES (?, ?, ?, ?, ?, ?, ?)',
            (stored.id, self._user, change.entry_id, change.changed_at.isoformat(), change.action,
             json.dumps(change.changes), change.detail),
        )
        return stored

    def history(self, entry_id: str) -> list[EntryChange]:
        sql = f'SELECT {_HISTORY_COLUMNS} FROM entry_history WHERE entry_id = ? AND user_id = ? ORDER BY id'
        rows = self._conn.execute(sql, (entry_id, self._user))
        return [_to_change(row) for row in rows]

    def all_history(self) -> list[EntryChange]:
        """The history of all the user's entries, deleted ones included, in the order it was written."""
        rows = self._conn.execute(f'SELECT {_HISTORY_COLUMNS} FROM entry_history WHERE user_id = ? ORDER BY id', (self._user,))
        return [_to_change(row) for row in rows]

    def changed(self, entry_ids: Iterable[str]) -> set[str]:
        """Those of the given entries that changed after they were created or imported (for the UI marker)."""
        ids = list(entry_ids)
        placeholders = ', '.join('?' for _ in ids)
        rows = self._conn.execute(
            f'SELECT DISTINCT entry_id FROM entry_history WHERE user_id = ? AND entry_id IN ({placeholders}) '
            'AND action NOT IN (?, ?)',
            (self._user, *ids, HistoryAction.CREATED, HistoryAction.IMPORTED),
        )
        return {row['entry_id'] for row in rows}

    def check_fits_day(self, entry: Entry) -> None:
        """An entry is at most as long as the rest of its day from the day's start (24:00 without a start time)."""
        row = self._conn.execute('SELECT start_time FROM days WHERE user_id = ? AND date = ?',
                                 (self._user, entry.date.isoformat())).fetchone()
        check_fits(entry, row[0] if row else None)

    def _check_references(self, entry: Entry) -> None:
        """An entry's ticket is created if needed; its activity type is one of the user's."""
        if entry.ticket_key:
            self._tickets.ensure(entry.ticket_key)
        if entry.activity_type_id is not None and not self._owned('activity_types', entry.activity_type_id):
            raise ConflictError(f'Cannot save entry: unknown activity type {entry.activity_type_id}')

    def _replace(self, old: Entry, entry: Entry) -> None:
        self._write(
            'UPDATE entries SET date = ?, activity_type_id = ?, ticket_key = ?, duration = ?, description = ? '
            'WHERE id = ? AND user_id = ?',
            (*_to_values(entry), entry.id, self._user),
        )

    def _remove(self, old: Entry) -> None:
        self._conn.execute('DELETE FROM entries WHERE id = ? AND user_id = ?', (old.id, self._user))

    def _owned(self, table: str, row_id: str) -> bool:
        row = self._conn.execute(f'SELECT 1 FROM {table} WHERE id = ? AND user_id = ?', (row_id, self._user)).fetchone()
        return row is not None

    def _write(self, sql: str, params: tuple) -> sqlite3.Cursor:
        try:
            return self._conn.execute(sql, params)
        except sqlite3.IntegrityError as error:
            raise ConflictError(f'Cannot save entry: {error}') from error


def check_fits(entry: Entry, start: int | None) -> None:
    """An entry is at most as long as the rest of its day from the day's start (24:00 without a start time)."""
    start = start or 0
    if entry.duration > MINUTES_PER_DAY - start:
        since = f' from {format_clock(start)} on' if start else ''
        raise ConflictError(f'Longer than the day allows: at most {format_duration(MINUTES_PER_DAY - start)}{since}')
