"""Export of a user's own data as one file (SPEC 5.8), with file ids in place of the database's."""

import datetime as dt
import re

from src.models.catalog import ActivityType, ServiceChoice, Ticket
from src.models.entries import ActivityEntry, Entry
from src.models.history import EntryChange, HistoryAction
from src.models.review import ReviewFlag
from src.models.schedules import Schedule
from src.modules.storage.store import Changes, Store
from src.modules.userdata.schemas import FORMAT, VERSION, UserData

SPLIT_FROM = re.compile(r'Split from entry (\d+)')  # the detail of an entry split off another one


class FileIds:
    """File ids 1, 2, … for database ids, in the order they are first asked for."""

    def __init__(self) -> None:
        self._ids: dict[int, int] = {}

    def __call__(self, db_id: int) -> int:
        return self._ids.setdefault(db_id, len(self._ids) + 1)

    def known(self, db_id: int | None) -> int | None:
        """The file id of a record in the file; None for one that is not (e.g. a deleted activity type)."""
        return self._ids.get(db_id)


def export_data(store: Store, user_id: str, exported_at: dt.datetime) -> UserData:
    """All records of the user; nothing of other users, teams, sessions or passwords."""
    return _Export(store, user_id).data(exported_at.replace(microsecond=0))


class _Export:
    def __init__(self, store: Store, user_id: str) -> None:
        self._store = store
        self._user = user_id
        self._services, self._activity_types, self._entries = FileIds(), FileIds(), FileIds()

    def data(self, exported_at: dt.datetime) -> UserData:
        tickets = self._store.tickets(self._user).all()
        services = self._services_of(tickets)  # numbered before the tickets and entries refer to them
        activity_types = self._activity_types_list()
        entries = self._entries_list()
        return UserData(
            format=FORMAT, version=VERSION, exported_at=exported_at, settings=self._store.load_settings(self._user),
            theme=self._store.load_theme(self._user), work_schedules=self._schedules(),
            pto_years=self._store.pto_years(self._user).all(), services=services, activity_types=activity_types,
            tickets=[ticket.model_copy(update={'service_id': self._services.known(ticket.service_id)}) for ticket in tickets],
            days=self._store.days(self._user).between(dt.date.min, dt.date.max), entries=entries,
            history=self._history(), review_flags=self._flags(),
        )

    def _services_of(self, tickets: list[Ticket]) -> list[ServiceChoice]:
        """The personal services, and the team services the tickets use."""
        used = {ticket.service_id for ticket in tickets}
        chosen = [service for service in self._store.services(self._user).choices() if not service.team or service.id in used]
        return [service.model_copy(update={'id': self._services(service.id)}) for service in chosen]

    def _activity_types_list(self) -> list[ActivityType]:
        return [kind.model_copy(update={'id': self._activity_types(kind.id)})
                for kind in self._store.activity_types(self._user).all()]

    def _schedules(self) -> list[Schedule]:
        schedules = self._store.schedules(self._user).all()
        return [schedule.model_copy(update={'id': number}) for number, schedule in enumerate(schedules, 1)]

    def _entries_list(self) -> list[Entry]:
        return [self._entry(entry) for entry in self._store.entries(self._user).between(dt.date.min, dt.date.max)]

    def _entry(self, entry: Entry) -> Entry:
        update: dict = {'id': self._entries(entry.id)}
        if isinstance(entry, ActivityEntry):
            update['activity_type_id'] = self._activity_types.known(entry.activity_type_id)
        return entry.model_copy(update=update)

    def _history(self) -> list[EntryChange]:
        """Deleted entries are only in the history; they get the file ids after the entries'."""
        return [
            change.model_copy(update={'id': number, 'entry_id': self._entries(change.entry_id),
                                      'changes': self._changes(change.changes), 'detail': self._detail(change)})
            for number, change in enumerate(self._store.entries(self._user).all_history(), 1)
        ]

    def _changes(self, changes: Changes) -> Changes:
        """Activity types named in a change by file id (None if no longer in the file)."""
        if 'activity_type_id' not in changes:
            return changes
        old, new = changes['activity_type_id']
        return changes | {'activity_type_id': (self._activity_types.known(old), self._activity_types.known(new))}

    def _detail(self, change: EntryChange) -> str:
        match = SPLIT_FROM.fullmatch(change.detail) if change.action == HistoryAction.SPLIT else None
        return f'Split from entry {self._entries(int(match[1]))}' if match else change.detail

    def _flags(self) -> list[ReviewFlag]:
        days, entries = self._store.days(self._user), self._store.entries(self._user)
        flags = [*days.day_flags(), *(flag.model_copy(update={'entry_id': self._entries(flag.entry_id)})
                                      for flag in entries.entry_flags())]
        return [flag.model_copy(update={'id': number}) for number, flag in enumerate(flags, 1)]
