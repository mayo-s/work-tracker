"""Task entries with their change history and review flags."""

import datetime as dt
import json
import sqlite3
from collections.abc import Callable, Iterable, Sequence

from pydantic import JsonValue

from src.lib.durations import MINUTES_PER_DAY, format_clock, format_duration, split_evenly
from src.models.base import new_id
from src.models.catalog import Ticket
from src.models.entries import ActivityEntry, Entry, TicketEntry
from src.models.history import EntryChange, HistoryAction
from src.models.review import FlagReason, ReviewFlag
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.store import Changes
from src.modules.storage.tickets import TicketRepository

_ENTRY_COLUMNS = 'id, date, kind, ticket_key, activity_type_id, duration, text, coding'
_HISTORY_COLUMNS = 'id, entry_id, changed_at, action, changes, detail'
_FLAG_COLUMNS = 'id, entry_id, reason, detail'


def history_time() -> dt.datetime:
    """The time of a history line, to the second."""
    return dt.datetime.now().replace(microsecond=0)


def _to_entry(row: sqlite3.Row) -> Entry:
    common = {'id': row['id'], 'date': row['date'], 'duration': row['duration']}
    if row['kind'] == 'ticket':
        return TicketEntry(**common, ticket_key=row['ticket_key'], description=row['text'], coding=bool(row['coding']))
    return ActivityEntry(**common, activity_type_id=row['activity_type_id'], note=row['text'])


def _to_values(entry: Entry) -> tuple:
    """Column values for date, kind, ticket_key, activity_type_id, duration, text, coding."""
    if isinstance(entry, TicketEntry):
        return entry.date.isoformat(), entry.kind, entry.ticket_key, None, entry.duration, entry.description, entry.coding
    return entry.date.isoformat(), entry.kind, None, entry.activity_type_id, entry.duration, entry.note, False


def entry_fields(entry: Entry) -> dict[str, JsonValue]:
    """The fields a history line records changes of."""
    return entry.model_dump(mode='json', exclude={'id', 'kind'})


def field_changes(old: dict[str, JsonValue], new: dict[str, JsonValue]) -> Changes:
    """Each changed field as (old, new); a new entry has no old values, a deleted one no new ones."""
    return {field: (old.get(field), new.get(field)) for field in old | new if old.get(field) != new.get(field)}


def _to_change(row: sqlite3.Row) -> EntryChange:
    return EntryChange(**{**dict(row), 'changes': json.loads(row['changes'])})


def _to_flag(row: sqlite3.Row) -> ReviewFlag:
    return ReviewFlag(id=row['id'], entry_id=row['entry_id'], reason=row['reason'], detail=row['detail'])


class EntryRules:
    """The rules of entries on every backend: creating, changing, splitting and deleting write the history, the kind of
    an entry stays. A backend's repository stores them: `get`, `restore`, `restore_history`, `_check_references`,
    `_replace` (an entry in place of its old version) and `_remove` (an entry and its review flags)."""

    _clock: Callable[[], dt.datetime]

    def create(self, entry: Entry, action: HistoryAction = HistoryAction.CREATED, detail: str = '') -> Entry:
        """Store a new entry; its ticket is created if needed. `action` is `created` or `imported`."""
        created = self.restore(entry)
        self.add_history(created.id, action, field_changes({}, entry_fields(created)), detail)
        return created

    def update(self, entry: Entry, action: HistoryAction = HistoryAction.UPDATED, detail: str = '') -> Entry:
        """Replace an entry; only changed fields are recorded. The kind of an entry cannot change."""
        old = self.get(entry.id)
        if old.kind != entry.kind:
            raise ConflictError(f'Entry {entry.id} is a {old.kind} entry, not a {entry.kind} entry')
        if changes := field_changes(entry_fields(old), entry_fields(entry)):
            self._check_references(entry)
            self._replace(old, entry)
            self.add_history(entry.id, action, changes, detail)
        return entry

    def split(self, entry_id: str, ticket_keys: Sequence[str]) -> list[Entry]:
        """Divide a ticket entry among several tickets, the hours split evenly in quarter hours.

        The entry itself gets the first ticket; the others become new entries with the same date and description.
        """
        entry = self.get(entry_id)
        keys = list(dict.fromkeys(Ticket(key=key).key for key in ticket_keys))
        if not isinstance(entry, TicketEntry) or len(keys) < 2:
            raise ConflictError('Only a ticket entry can be split, into at least two different tickets')
        shares = split_evenly(entry.duration, len(keys))
        first = self.update(
            entry.model_copy(update={'ticket_key': keys[0], 'duration': shares[0]}), HistoryAction.SPLIT,
            f'Split into {", ".join(keys)}',
        )
        others = [
            self.create(entry.model_copy(update={'id': None, 'ticket_key': key, 'duration': share}), HistoryAction.SPLIT,
                        f'Split from entry {entry_id}')
            for key, share in zip(keys[1:], shares[1:])
        ]
        return [first, *others]

    def delete(self, entry_id: str) -> None:
        """Delete an entry and its review flags; its history is kept."""
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
    """Ticket and activity entries of one user; every change is written to the entry's history.

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
        """Entries with 0:00, ticket entries without ticket and flagged entries, by date."""
        rows = self._conn.execute(
            f'SELECT {_ENTRY_COLUMNS} FROM entries '
            "WHERE user_id = ? AND (duration = 0 OR (kind = 'ticket' AND ticket_key IS NULL) "
            'OR id IN (SELECT entry_id FROM review_flags WHERE entry_id IS NOT NULL)) ORDER BY date, id',
            (self._user,),
        )
        return [_to_entry(row) for row in rows]

    def restore(self, entry: Entry) -> Entry:
        """Store an entry without a history line (its history comes along, e.g. from an export file); its ticket is
        created if needed."""
        self._check_references(entry)
        restored = entry.model_copy(update={'id': new_id()})
        self._write(
            'INSERT INTO entries (id, user_id, date, kind, ticket_key, activity_type_id, duration, text, coding) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
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

    def imported_lines(self, entry_ids: Iterable[str]) -> dict[str, str]:
        """The original spreadsheet line of each of the given entries that was imported."""
        ids = list(entry_ids)
        placeholders = ', '.join('?' for _ in ids)
        rows = self._conn.execute(
            f'SELECT entry_id, detail FROM entry_history WHERE user_id = ? AND entry_id IN ({placeholders}) AND action = ?',
            (self._user, *ids, HistoryAction.IMPORTED),
        )
        return {row['entry_id']: row['detail'] for row in rows}

    def add_flag(self, entry_id: str, reason: FlagReason, detail: str = '') -> ReviewFlag:
        flag = ReviewFlag(entry_id=entry_id, reason=reason, detail=detail)
        if not self._owned('entries', entry_id):
            raise ConflictError(f'Cannot flag entry {entry_id}: no such entry')
        added = flag.model_copy(update={'id': new_id()})
        self._write('INSERT INTO review_flags (id, user_id, entry_id, reason, detail) VALUES (?, ?, ?, ?, ?)',
                    (added.id, self._user, entry_id, flag.reason, flag.detail))
        return added

    def flags_of(self, entry_id: str) -> list[ReviewFlag]:
        rows = self._conn.execute(f'SELECT {_FLAG_COLUMNS} FROM review_flags WHERE entry_id = ? AND user_id = ? ORDER BY id',
                                  (entry_id, self._user))
        return [_to_flag(row) for row in rows]

    def entry_flags(self) -> list[ReviewFlag]:
        """All flags on entries, in the order they were added."""
        sql = f'SELECT {_FLAG_COLUMNS} FROM review_flags WHERE user_id = ? AND entry_id IS NOT NULL ORDER BY id'
        rows = self._conn.execute(sql, (self._user,))
        return [_to_flag(row) for row in rows]

    def clear_flag(self, flag_id: str) -> None:
        sql = 'DELETE FROM review_flags WHERE id = ? AND user_id = ? AND entry_id IS NOT NULL'
        if not self._conn.execute(sql, (flag_id, self._user)).rowcount:
            raise NotFoundError(f'No entry flag with id {flag_id}')

    def check_fits_day(self, entry: Entry) -> None:
        """An entry is at most as long as the rest of its day from the day's start (24:00 without a start time)."""
        row = self._conn.execute('SELECT start_time FROM days WHERE user_id = ? AND date = ?',
                                 (self._user, entry.date.isoformat())).fetchone()
        check_fits(entry, row[0] if row else None)

    def _check_references(self, entry: Entry) -> None:
        """A ticket entry's ticket is created if needed; an activity entry needs one of the user's activity types."""
        if isinstance(entry, TicketEntry) and entry.ticket_key:
            self._tickets.ensure(entry.ticket_key)
        if isinstance(entry, ActivityEntry) and not self._owned('activity_types', entry.activity_type_id):
            raise ConflictError(f'Cannot save entry: unknown activity type {entry.activity_type_id}')

    def _replace(self, old: Entry, entry: Entry) -> None:
        self._write(
            'UPDATE entries SET date = ?, kind = ?, ticket_key = ?, activity_type_id = ?, duration = ?, text = ?, '
            'coding = ? WHERE id = ? AND user_id = ?',
            (*_to_values(entry), entry.id, self._user),
        )

    def _remove(self, old: Entry) -> None:
        self._conn.execute('DELETE FROM entries WHERE id = ? AND user_id = ?', (old.id, self._user))  # flags cascade

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
