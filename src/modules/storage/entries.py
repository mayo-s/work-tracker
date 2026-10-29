"""Task entries with their change history and review flags."""

import datetime as dt
import json
import sqlite3
from collections.abc import Callable, Iterable, Sequence

from pydantic import JsonValue

from src.lib.durations import split_evenly
from src.models.catalog import Ticket
from src.models.entries import ActivityEntry, Entry, TicketEntry
from src.models.history import EntryChange, HistoryAction
from src.models.review import FlagReason, ReviewFlag
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.tickets import TicketRepository

Changes = dict[str, tuple[JsonValue, JsonValue]]

_ENTRY_COLUMNS = 'id, date, kind, ticket_key, activity_type_id, duration, text, coding'
_HISTORY_COLUMNS = 'id, entry_id, changed_at, action, changes, detail'
_FLAG_COLUMNS = 'id, entry_id, reason, detail'


def _now() -> dt.datetime:
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


def _fields(entry: Entry) -> dict[str, JsonValue]:
    return entry.model_dump(mode='json', exclude={'id', 'kind'})


def _diff(old: dict[str, JsonValue], new: dict[str, JsonValue]) -> Changes:
    return {field: (old.get(field), new.get(field)) for field in old | new if old.get(field) != new.get(field)}


def _to_change(row: sqlite3.Row) -> EntryChange:
    return EntryChange(**{**dict(row), 'changes': json.loads(row['changes'])})


def _to_flag(row: sqlite3.Row) -> ReviewFlag:
    return ReviewFlag(id=row['id'], entry_id=row['entry_id'], reason=row['reason'], detail=row['detail'])


class EntryRepository:
    """Ticket and activity entries of one user; every change is written to the entry's history.

    Works within the transaction of the given connection. `clock` provides the history timestamps.
    """

    def __init__(self, conn: sqlite3.Connection, user_id: str, clock: Callable[[], dt.datetime] | None = None) -> None:
        self._conn = conn
        self._user = user_id
        self._clock = clock or _now
        self._tickets = TicketRepository(conn, user_id)

    def get(self, entry_id: int) -> Entry:
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

    def imported_together(self, entry_id: int) -> list[Entry]:
        """Entries imported from the same spreadsheet line as this one (same date and original line), itself included.

        Empty if the entry was not imported.
        """
        rows = self._conn.execute(
            f'SELECT {", ".join(f"e.{column}" for column in _ENTRY_COLUMNS.split(", "))} FROM entries e '
            "JOIN entry_history h ON h.entry_id = e.id AND h.action = 'imported' "
            "JOIN entry_history own ON own.entry_id = ? AND own.action = 'imported' "
            'JOIN entries mine ON mine.id = own.entry_id AND mine.user_id = e.user_id '
            'WHERE h.detail = own.detail AND e.date = mine.date AND e.user_id = ? ORDER BY e.id',
            (entry_id, self._user),
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

    def create(self, entry: Entry, action: HistoryAction = HistoryAction.CREATED, detail: str = '') -> Entry:
        """Store a new entry; its ticket is created if needed. `action` is `created` or `imported`."""
        self._check_references(entry)
        cursor = self._write(
            'INSERT INTO entries (user_id, date, kind, ticket_key, activity_type_id, duration, text, coding) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (self._user, *_to_values(entry)),
        )
        created = entry.model_copy(update={'id': cursor.lastrowid})
        self.add_history(created.id, action, _diff({}, _fields(created)), detail)
        return created

    def update(self, entry: Entry, action: HistoryAction = HistoryAction.UPDATED, detail: str = '') -> Entry:
        """Replace an entry; only changed fields are recorded. The kind of an entry cannot change."""
        old = self.get(entry.id)
        if old.kind != entry.kind:
            raise ConflictError(f'Entry {entry.id} is a {old.kind} entry, not a {entry.kind} entry')
        if changes := _diff(_fields(old), _fields(entry)):
            self._check_references(entry)
            self._write(
                'UPDATE entries SET date = ?, kind = ?, ticket_key = ?, activity_type_id = ?, duration = ?, text = ?, '
                'coding = ? WHERE id = ? AND user_id = ?',
                (*_to_values(entry), entry.id, self._user),
            )
            self.add_history(entry.id, action, changes, detail)
        return entry

    def split(self, entry_id: int, ticket_keys: Sequence[str]) -> list[Entry]:
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

    def delete(self, entry_id: int) -> None:
        """Delete an entry and its review flags; its history is kept."""
        old = self.get(entry_id)
        self._conn.execute('DELETE FROM entries WHERE id = ? AND user_id = ?', (entry_id, self._user))
        self.add_history(entry_id, HistoryAction.DELETED, _diff(_fields(old), {}))

    def add_history(self, entry_id: int, action: HistoryAction, changes: Changes, detail: str = '') -> EntryChange:
        change = EntryChange(entry_id=entry_id, changed_at=self._clock(), action=action, changes=changes, detail=detail)
        cursor = self._conn.execute(
            'INSERT INTO entry_history (user_id, entry_id, changed_at, action, changes, detail) VALUES (?, ?, ?, ?, ?, ?)',
            (self._user, entry_id, change.changed_at.isoformat(), change.action, json.dumps(change.changes), change.detail),
        )
        return change.model_copy(update={'id': cursor.lastrowid})

    def history(self, entry_id: int) -> list[EntryChange]:
        sql = f'SELECT {_HISTORY_COLUMNS} FROM entry_history WHERE entry_id = ? AND user_id = ? ORDER BY id'
        rows = self._conn.execute(sql, (entry_id, self._user))
        return [_to_change(row) for row in rows]

    def changed(self, entry_ids: Iterable[int]) -> set[int]:
        """Those of the given entries that changed after they were created or imported (for the UI marker)."""
        ids = list(entry_ids)
        placeholders = ', '.join('?' for _ in ids)
        rows = self._conn.execute(
            f'SELECT DISTINCT entry_id FROM entry_history WHERE user_id = ? AND entry_id IN ({placeholders}) '
            'AND action NOT IN (?, ?)',
            (self._user, *ids, HistoryAction.CREATED, HistoryAction.IMPORTED),
        )
        return {row['entry_id'] for row in rows}

    def add_flag(self, entry_id: int, reason: FlagReason, detail: str = '') -> ReviewFlag:
        flag = ReviewFlag(entry_id=entry_id, reason=reason, detail=detail)
        if not self._owned('entries', entry_id):
            raise ConflictError(f'Cannot flag entry {entry_id}: no such entry')
        cursor = self._write('INSERT INTO review_flags (user_id, entry_id, reason, detail) VALUES (?, ?, ?, ?)',
                             (self._user, entry_id, flag.reason, flag.detail))
        return flag.model_copy(update={'id': cursor.lastrowid})

    def flags_of(self, entry_id: int) -> list[ReviewFlag]:
        rows = self._conn.execute(f'SELECT {_FLAG_COLUMNS} FROM review_flags WHERE entry_id = ? AND user_id = ? ORDER BY id',
                                  (entry_id, self._user))
        return [_to_flag(row) for row in rows]

    def entry_flags(self) -> list[ReviewFlag]:
        """All flags on entries, in the order they were added."""
        sql = f'SELECT {_FLAG_COLUMNS} FROM review_flags WHERE user_id = ? AND entry_id IS NOT NULL ORDER BY id'
        rows = self._conn.execute(sql, (self._user,))
        return [_to_flag(row) for row in rows]

    def clear_flag(self, flag_id: int) -> None:
        sql = 'DELETE FROM review_flags WHERE id = ? AND user_id = ? AND entry_id IS NOT NULL'
        if not self._conn.execute(sql, (flag_id, self._user)).rowcount:
            raise NotFoundError(f'No entry flag with id {flag_id}')

    def _check_references(self, entry: Entry) -> None:
        """A ticket entry's ticket is created if needed; an activity entry needs one of the user's activity types."""
        if isinstance(entry, TicketEntry) and entry.ticket_key:
            self._tickets.ensure(entry.ticket_key)
        if isinstance(entry, ActivityEntry) and not self._owned('activity_types', entry.activity_type_id):
            raise ConflictError(f'Cannot save entry: unknown activity type {entry.activity_type_id}')

    def _owned(self, table: str, row_id: int) -> bool:
        row = self._conn.execute(f'SELECT 1 FROM {table} WHERE id = ? AND user_id = ?', (row_id, self._user)).fetchone()
        return row is not None

    def _write(self, sql: str, params: tuple) -> sqlite3.Cursor:
        try:
            return self._conn.execute(sql, params)
        except sqlite3.IntegrityError as error:
            raise ConflictError(f'Cannot save entry: {error}') from error
