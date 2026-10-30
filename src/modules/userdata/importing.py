"""Import of an export file (SPEC 5.8) for a user without days and entries, e.g. in the setup on another installation."""

import datetime as dt

from src.models.catalog import ActivityType, Service
from src.models.entries import ActivityEntry
from src.models.history import EntryChange, HistoryAction
from src.modules.storage.errors import ConflictError
from src.modules.storage.store import Changes, Entries, Store
from src.modules.userdata.export import SPLIT_FROM
from src.modules.userdata.schemas import ImportSummary, UserData


def import_data(store: Store, user_id: str, data: UserData) -> ImportSummary:
    """Write the file's records for the user, with database ids in place of the file's. Team services become personal
    ones (an own service with the same short name is used instead), and the file's activity types replace the user's.

    Refused (ConflictError) for a user who has days or entries, and for a file referring to records it does not hold.
    It runs in the caller's transaction, so a failure leaves nothing behind.
    """
    return _Import(store, user_id, data).run()


class _Import:
    def __init__(self, store: Store, user_id: str, data: UserData) -> None:
        self._store = store
        self._user = user_id
        self._data = data
        self._services: dict[int, int] = {}  # file id → database id
        self._activity_types: dict[int, int] = {}
        self._entries: dict[int, int] = {}

    def run(self) -> ImportSummary:
        self._check_empty()
        self._settings()
        self._services_of_file()
        self._activity_types_of_file()
        self._tickets()
        days = self._store.days(self._user)
        for day in self._data.days:
            days.save(day)
        self._entries_of_file()
        self._history()
        self._flags()
        data = self._data
        return ImportSummary(
            work_schedules=len(data.work_schedules), pto_years=len(data.pto_years), services=len(data.services),
            activity_types=len(data.activity_types), tickets=len(data.tickets), days=len(data.days),
            entries=len(data.entries), history=len(data.history), review_flags=len(data.review_flags),
        )

    def _check_empty(self) -> None:
        entries = self._store.entries(self._user)
        if self._store.days(self._user).between(dt.date.min, dt.date.max) or entries.all_history():
            raise ConflictError('Only an account without days and entries can import a file; this one has some')

    def _settings(self) -> None:
        self._store.save_settings(self._user, self._data.settings)
        self._store.save_theme(self._user, self._data.theme)
        schedules = self._store.schedules(self._user)
        if self._data.work_schedules:
            first, *later = self._data.work_schedules
            schedules.replace_all(first)
            for schedule in later:
                schedules.add(schedule)
        self._store.pto_years(self._user).replace_all(self._data.pto_years)

    def _services_of_file(self) -> None:
        """Personal services first, so a team service with the same short name uses the personal one."""
        services = self._store.services(self._user)
        by_name = {service.short_name.casefold(): service.id for service in services.all()}
        for service in sorted(self._data.services, key=lambda service: service.team is not None):
            name = service.short_name.casefold()
            if name not in by_name:
                by_name[name] = services.add(Service(short_name=service.short_name, name=service.name)).id
            self._services[service.id] = by_name[name]

    def _activity_types_of_file(self) -> None:
        """The file's activity types replace the user's (the defaults; without entries none is in use)."""
        kinds = self._store.activity_types(self._user)
        for kind in kinds.all():
            kinds.delete(kind.id)
        for kind in self._data.activity_types:
            self._activity_types[kind.id] = kinds.add(ActivityType(name=kind.name)).id

    def _tickets(self) -> None:
        tickets = self._store.tickets(self._user)
        for ticket in self._data.tickets:
            tickets.ensure(ticket.key)
            if ticket.service_id is not None:
                tickets.set_service(ticket.key, _known(self._services, ticket.service_id, 'service'))

    def _entries_of_file(self) -> None:
        entries = self._store.entries(self._user)
        for entry in self._data.entries:
            update: dict = {'id': None}
            if isinstance(entry, ActivityEntry):
                update['activity_type_id'] = _known(self._activity_types, entry.activity_type_id, 'activity type')
            self._entries[entry.id] = entries.restore(entry.model_copy(update=update)).id

    def _history(self) -> None:
        """Entries only in the history (deleted before the export) get reserved ids, in the order they come up."""
        entries = self._store.entries(self._user)
        for change in self._data.history:
            entry_id = self._entry_id(entries, change.entry_id)
            entries.restore_history(change.model_copy(update={
                'id': None, 'entry_id': entry_id, 'changes': self._changes(change.changes),
                'detail': self._detail(entries, change),
            }))

    def _entry_id(self, entries: Entries, file_id: int) -> int:
        if file_id not in self._entries:
            self._entries[file_id] = entries.reserve_id()
        return self._entries[file_id]

    def _changes(self, changes: Changes) -> Changes:
        """Activity types named in a change by database id (None if the file does not hold them)."""
        if 'activity_type_id' not in changes:
            return changes
        old, new = changes['activity_type_id']
        return changes | {'activity_type_id': (self._activity_types.get(old), self._activity_types.get(new))}

    def _detail(self, entries: Entries, change: EntryChange) -> str:
        match = SPLIT_FROM.fullmatch(change.detail) if change.action == HistoryAction.SPLIT else None
        return f'Split from entry {self._entry_id(entries, int(match[1]))}' if match else change.detail

    def _flags(self) -> None:
        days, entries = self._store.days(self._user), self._store.entries(self._user)
        for flag in self._data.review_flags:
            if flag.date is not None:
                days.add_flag(flag.date, flag.reason, flag.detail)
            else:
                entries.add_flag(_known(self._entries, flag.entry_id, 'entry'), flag.reason, flag.detail)


def _known(ids: dict[int, int], file_id: int, label: str) -> int:
    if file_id not in ids:
        raise ConflictError(f'The file refers to {label} {file_id}, which it does not hold')
    return ids[file_id]
