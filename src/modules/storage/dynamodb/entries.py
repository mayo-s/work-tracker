"""Task entries with their history and review flags on DynamoDB, with the rules of the SQLite repository (entries.py).

In the user's partition: `ENTRY#<date>#<id>` (the entry, so a period is one query in date and creation order),
`ENTRY_ID#<id>` (its date, to find it by id) and `HISTORY#<entry id>#<id>` (its history, kept after it is deleted).
"""

import datetime as dt
from collections.abc import Callable, Iterable, Sequence

from pydantic import TypeAdapter

from src.lib.durations import split_evenly
from src.models.catalog import Ticket
from src.models.entries import ActivityEntry, Entry, TicketEntry
from src.models.history import EntryChange, HistoryAction
from src.models.review import FlagReason, ReviewFlag
from src.modules.storage.dynamodb.catalog import activity_type_key
from src.modules.storage.dynamodb.days import day_key
from src.modules.storage.dynamodb.flags import add_flag, all_flags, delete_flags, flag_key
from src.modules.storage.dynamodb.keys import user_partition
from src.modules.storage.dynamodb.table import Item, attributes
from src.modules.storage.dynamodb.tickets import ensure_ticket
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.entries import check_fits, entry_fields, field_changes, history_time
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.store import Changes

_ENTRY = TypeAdapter(Entry)
_LAST = '\U0010ffff'  # sorts after every other character, as the end of a sort key range


def _entry_key(date: dt.date | str, entry_id: int) -> str:
    return f'ENTRY#{date}#{entry_id:010d}'


def _id_key(entry_id: int) -> str:
    return f'ENTRY_ID#{entry_id:010d}'


def _history_key(entry_id: int, change_id: int) -> str:
    return f'HISTORY#{entry_id:010d}#{change_id:010d}'


def _entry(item: Item) -> Entry:
    return _ENTRY.validate_python(attributes(item))


def _incomplete(entry: Entry) -> bool:
    """0:00, or a ticket entry without a ticket."""
    return entry.duration == 0 or (isinstance(entry, TicketEntry) and entry.ticket_key is None)


class DynamoEntries:
    """Ticket and activity entries of one user; every change is written to the entry's history. `clock` provides the
    history timestamps."""

    def __init__(self, unit: Unit, user_id: str, clock: Callable[[], dt.datetime] | None = None) -> None:
        self._unit = unit
        self._pk = user_partition(user_id)
        self._clock = clock or history_time

    def get(self, entry_id: int) -> Entry:
        pointer = self._unit.get(self._pk, _id_key(entry_id))
        item = pointer and self._unit.get(self._pk, _entry_key(pointer['date'], entry_id))
        if not item:
            raise NotFoundError(f'No entry with id {entry_id}')
        return _entry(item)

    def between(self, start: dt.date, end: dt.date) -> list[Entry]:
        """Entries from start to end (inclusive), by date and in the order they were created."""
        items = self._unit.query(self._pk, f'ENTRY#{start.isoformat()}', f'ENTRY#{end.isoformat()}#{_LAST}')
        return [_entry(item) for item in items]

    def imported_together(self, entry_id: int) -> list[Entry]:
        """Entries imported from the same spreadsheet line as this one (same date and original line), itself included.

        Empty if the entry was not imported.
        """
        line, pointer = self._imported_line(entry_id), self._unit.get(self._pk, _id_key(entry_id))
        if line is None or pointer is None:
            return []
        date = dt.date.fromisoformat(pointer['date'])
        return [entry for entry in self.between(date, date) if self._imported_line(entry.id) == line]

    def for_review(self) -> list[Entry]:
        """Entries with 0:00, ticket entries without ticket and flagged entries, by date."""
        flagged = {flag.entry_id for flag in all_flags(self._unit, self._pk) if flag.entry_id is not None}
        return [entry for entry in self.between(dt.date.min, dt.date.max) if entry.id in flagged or _incomplete(entry)]

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
            self._unit.delete(self._pk, _entry_key(old.date.isoformat(), old.id))  # the date is in the key
            self._save(entry)
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
        self._unit.delete(self._pk, _entry_key(old.date.isoformat(), entry_id))
        self._unit.delete(self._pk, _id_key(entry_id))
        delete_flags(self._unit, self._pk, lambda flag: flag.entry_id == entry_id)
        self.add_history(entry_id, HistoryAction.DELETED, field_changes(entry_fields(old), {}))

    def restore(self, entry: Entry) -> Entry:
        """Store an entry without a history line (its history comes along, e.g. from an export file); its ticket is
        created if needed."""
        self._check_references(entry)
        restored = entry.model_copy(update={'id': self._unit.next_id('entry')})
        self._save(restored)
        return restored

    def reserve_id(self) -> int:
        """An id no entry will get, for an entry known only from its history (deleted before an export)."""
        return self._unit.next_id('entry')

    def restore_history(self, change: EntryChange) -> EntryChange:
        """Store a history line as it was, with its own time."""
        stored = change.model_copy(update={'id': self._unit.next_id('history')})
        self._unit.put({'PK': self._pk, 'SK': _history_key(stored.entry_id, stored.id), **stored.model_dump(mode='json')})
        return stored

    def add_history(self, entry_id: int, action: HistoryAction, changes: Changes, detail: str = '') -> EntryChange:
        return self.restore_history(
            EntryChange(entry_id=entry_id, changed_at=self._clock(), action=action, changes=changes, detail=detail))

    def history(self, entry_id: int) -> list[EntryChange]:
        return [EntryChange(**attributes(item)) for item in self._unit.query_prefix(self._pk, f'HISTORY#{entry_id:010d}#')]

    def all_history(self) -> list[EntryChange]:
        """The history of all the user's entries, deleted ones included, in the order it was written."""
        changes = [EntryChange(**attributes(item)) for item in self._unit.query_prefix(self._pk, 'HISTORY#')]
        return sorted(changes, key=lambda change: change.id)

    def changed(self, entry_ids: Iterable[int]) -> set[int]:
        """Those of the given entries that changed after they were created or imported (for the UI marker)."""
        ids = set(entry_ids)
        if not ids:
            return set()
        lines = self._unit.query(self._pk, f'HISTORY#{min(ids):010d}#', f'HISTORY#{max(ids):010d}#{_LAST}')
        return {line['entry_id'] for line in lines if line['entry_id'] in ids
                and line['action'] not in (HistoryAction.CREATED, HistoryAction.IMPORTED)}

    def add_flag(self, entry_id: int, reason: FlagReason, detail: str = '') -> ReviewFlag:
        flag = ReviewFlag(entry_id=entry_id, reason=reason, detail=detail)
        if self._unit.get(self._pk, _id_key(entry_id)) is None:
            raise ConflictError(f'Cannot flag entry {entry_id}: no such entry')
        return add_flag(self._unit, self._pk, flag)

    def flags_of(self, entry_id: int) -> list[ReviewFlag]:
        return [flag for flag in all_flags(self._unit, self._pk) if flag.entry_id == entry_id]

    def entry_flags(self) -> list[ReviewFlag]:
        """All flags on entries, in the order they were added."""
        return [flag for flag in all_flags(self._unit, self._pk) if flag.entry_id is not None]

    def clear_flag(self, flag_id: int) -> None:
        item = self._unit.get(self._pk, flag_key(flag_id))
        if item is None or item['entry_id'] is None:
            raise NotFoundError(f'No entry flag with id {flag_id}')
        self._unit.delete(self._pk, flag_key(flag_id))

    def check_fits_day(self, entry: Entry) -> None:
        """An entry is at most as long as the rest of its day from the day's start (24:00 without a start time)."""
        day = self._unit.get(self._pk, day_key(entry.date))
        check_fits(entry, day['start'] if day else None)

    def _imported_line(self, entry_id: int) -> str | None:
        return next((change.detail for change in self.history(entry_id) if change.action == HistoryAction.IMPORTED), None)

    def _check_references(self, entry: Entry) -> None:
        """A ticket entry's ticket is created if needed; an activity entry needs one of the user's activity types."""
        if isinstance(entry, TicketEntry) and entry.ticket_key:
            ensure_ticket(self._unit, self._pk, entry.ticket_key)
        if isinstance(entry, ActivityEntry) and not self._unit.get(self._pk, activity_type_key(entry.activity_type_id)):
            raise ConflictError(f'Cannot save entry: unknown activity type {entry.activity_type_id}')

    def _save(self, entry: Entry) -> None:
        self._unit.put({'PK': self._pk, 'SK': _entry_key(entry.date.isoformat(), entry.id), **entry.model_dump(mode='json')})
        self._unit.put({'PK': self._pk, 'SK': _id_key(entry.id), 'date': entry.date.isoformat()})
