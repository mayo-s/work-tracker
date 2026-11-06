"""Task entries with their history and review flags on DynamoDB, with the rules of the SQLite repository (entries.py).

In the user's partition: `ENTRY#<date>#<id>` (the entry, so a period is one query in date and creation order),
`ENTRY_ID#<id>` (its date, to find it by id) and `HISTORY#<entry id>#<id>` (its history, kept after it is deleted).
"""

import datetime as dt
from collections.abc import Callable, Iterable

from pydantic import TypeAdapter

from src.models.base import new_id
from src.models.entries import Entry
from src.models.history import EntryChange, HistoryAction
from src.models.review import FlagReason, ReviewFlag
from src.modules.storage.dynamodb.catalog import ACTIVITY_TYPE, activity_type_key
from src.modules.storage.dynamodb.days import day_key
from src.modules.storage.dynamodb.flags import add_flag, all_flags, delete_flags, flag_key
from src.modules.storage.dynamodb.keys import user_partition
from src.modules.storage.dynamodb.table import Item, attributes
from src.modules.storage.dynamodb.tickets import ensure_ticket
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.entries import EntryRules, check_fits, history_time
from src.modules.storage.errors import ConflictError, NotFoundError

_ENTRY = TypeAdapter(Entry)
_LAST = '\U0010ffff'  # sorts after every other character, as the end of a sort key range


def _entry_key(date: dt.date | str, entry_id: str) -> str:
    return f'ENTRY#{date}#{entry_id}'


def _id_key(entry_id: str) -> str:
    return f'ENTRY_ID#{entry_id}'


def _history_key(entry_id: str, change_id: str) -> str:
    return f'HISTORY#{entry_id}#{change_id}'


def _entry(item: Item) -> Entry:
    return _ENTRY.validate_python(attributes(item))


def _incomplete(entry: Entry, ticket_required: set[str]) -> bool:
    """0:00, no activity type, or no ticket though the activity type requires one."""
    return (entry.duration == 0 or entry.activity_type_id is None
            or (entry.ticket_key is None and entry.activity_type_id in ticket_required))


class DynamoEntries(EntryRules):
    """Task entries of one user; every change is written to the entry's history. `clock` provides the
    history timestamps."""

    def __init__(self, unit: Unit, user_id: str, clock: Callable[[], dt.datetime] | None = None) -> None:
        self._unit = unit
        self._pk = user_partition(user_id)
        self._clock = clock or history_time

    def get(self, entry_id: str) -> Entry:
        pointer = self._unit.get(self._pk, _id_key(entry_id))
        item = pointer and self._unit.get(self._pk, _entry_key(pointer['date'], entry_id))
        if not item:
            raise NotFoundError(f'No entry with id {entry_id}')
        return _entry(item)

    def between(self, start: dt.date, end: dt.date) -> list[Entry]:
        """Entries from start to end (inclusive), by date and in the order they were created."""
        items = self._unit.query(self._pk, f'ENTRY#{start.isoformat()}', f'ENTRY#{end.isoformat()}#{_LAST}')
        return [_entry(item) for item in items]

    def for_review(self) -> list[Entry]:
        """Entries with 0:00, without activity type, without the ticket their activity type requires, and flagged
        entries, by date."""
        flagged = {flag.entry_id for flag in all_flags(self._unit, self._pk) if flag.entry_id is not None}
        required = self._ticket_required()
        return [entry for entry in self.between(dt.date.min, dt.date.max)
                if entry.id in flagged or _incomplete(entry, required)]

    def _ticket_required(self) -> set[str]:
        """The ids of the activity types that require a ticket."""
        return {item['id'] for item in self._unit.query_prefix(self._pk, ACTIVITY_TYPE) if item.get('ticket_required')}

    def restore(self, entry: Entry) -> Entry:
        """Store an entry without a history line (its history comes along, e.g. from an export file); its ticket is
        created if needed."""
        self._check_references(entry)
        restored = entry.model_copy(update={'id': new_id()})
        self._save(restored)
        return restored

    def restore_history(self, change: EntryChange) -> EntryChange:
        """Store a history line as it was, with its own time."""
        stored = change.model_copy(update={'id': new_id()})
        self._unit.put({'PK': self._pk, 'SK': _history_key(stored.entry_id, stored.id), **stored.model_dump(mode='json')})
        return stored

    def history(self, entry_id: str) -> list[EntryChange]:
        return [EntryChange(**attributes(item)) for item in self._unit.query_prefix(self._pk, f'HISTORY#{entry_id}#')]

    def all_history(self) -> list[EntryChange]:
        """The history of all the user's entries, deleted ones included, in the order it was written."""
        changes = [EntryChange(**attributes(item)) for item in self._unit.query_prefix(self._pk, 'HISTORY#')]
        return sorted(changes, key=lambda change: change.id)

    def changed(self, entry_ids: Iterable[str]) -> set[str]:
        """Those of the given entries that changed after they were created or imported (for the UI marker)."""
        return {line['entry_id'] for line in self._history_of(entry_ids)
                if line['action'] not in (HistoryAction.CREATED, HistoryAction.IMPORTED)}

    def imported_lines(self, entry_ids: Iterable[str]) -> dict[str, str]:
        """The original spreadsheet line of each of the given entries that was imported."""
        return {line['entry_id']: line['detail'] for line in self._history_of(entry_ids)
                if line['action'] == HistoryAction.IMPORTED}

    def add_flag(self, entry_id: str, reason: FlagReason, detail: str = '') -> ReviewFlag:
        flag = ReviewFlag(entry_id=entry_id, reason=reason, detail=detail)
        if self._unit.get(self._pk, _id_key(entry_id)) is None:
            raise ConflictError(f'Cannot flag entry {entry_id}: no such entry')
        return add_flag(self._unit, self._pk, flag)

    def flags_of(self, entry_id: str) -> list[ReviewFlag]:
        return [flag for flag in all_flags(self._unit, self._pk) if flag.entry_id == entry_id]

    def entry_flags(self) -> list[ReviewFlag]:
        """All flags on entries, in the order they were added."""
        return [flag for flag in all_flags(self._unit, self._pk) if flag.entry_id is not None]

    def clear_flag(self, flag_id: str) -> None:
        item = self._unit.get(self._pk, flag_key(flag_id))
        if item is None or item['entry_id'] is None:
            raise NotFoundError(f'No entry flag with id {flag_id}')
        self._unit.delete(self._pk, flag_key(flag_id))

    def check_fits_day(self, entry: Entry) -> None:
        """An entry is at most as long as the rest of its day from the day's start (24:00 without a start time)."""
        day = self._unit.get(self._pk, day_key(entry.date))
        check_fits(entry, day['start'] if day else None)

    def _history_of(self, entry_ids: Iterable[str]) -> list[Item]:
        """The history lines of the given entries, in one query (from the lowest to the highest id)."""
        ids = set(entry_ids)
        if not ids:
            return []
        lines = self._unit.query(self._pk, f'HISTORY#{min(ids)}#', f'HISTORY#{max(ids)}#{_LAST}')
        return [line for line in lines if line['entry_id'] in ids]

    def _check_references(self, entry: Entry) -> None:
        """An entry's ticket is created if needed; its activity type is one of the user's."""
        if entry.ticket_key:
            ensure_ticket(self._unit, self._pk, entry.ticket_key)
        if entry.activity_type_id is not None and not self._unit.get(self._pk, activity_type_key(entry.activity_type_id)):
            raise ConflictError(f'Cannot save entry: unknown activity type {entry.activity_type_id}')

    def _replace(self, old: Entry, entry: Entry) -> None:
        self._unit.delete(self._pk, _entry_key(old.date.isoformat(), old.id))  # the date is in the key
        self._save(entry)

    def _remove(self, old: Entry) -> None:
        self._unit.delete(self._pk, _entry_key(old.date.isoformat(), old.id))
        self._unit.delete(self._pk, _id_key(old.id))
        delete_flags(self._unit, self._pk, lambda flag: flag.entry_id == old.id)

    def _save(self, entry: Entry) -> None:
        self._unit.put({'PK': self._pk, 'SK': _entry_key(entry.date.isoformat(), entry.id), **entry.model_dump(mode='json')})
        self._unit.put({'PK': self._pk, 'SK': _id_key(entry.id), 'date': entry.date.isoformat()})
