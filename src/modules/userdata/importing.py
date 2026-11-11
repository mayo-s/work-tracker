"""Import of an export file (SPEC 5.8) for a user without days and entries, e.g. in the setup on another installation."""

import datetime as dt
from collections.abc import Iterable

from src.models.catalog import Service
from src.models.history import EntryChange, HistoryAction
from src.modules.storage.errors import ConflictError
from src.modules.storage.store import Changes, Entries, Store
from src.modules.userdata.export import SPLIT_FROM
from src.modules.userdata.schemas import ImportSummary, UserData

ROOM = 4  # the most items one record of the file takes, e.g. an entry with its pointer and its new ticket on DynamoDB


def import_data(store: Store, user_id: str, data: UserData, team_services: dict[str, str] | None = None) -> ImportSummary:
    """Write the file's records for the user, with new record ids in place of the file's. Team services become personal
    ones (an own service with the same short name is used instead), except those in `team_services` (short name in
    lower case → id of the service of the user's team; the full restore), and the file's activity types replace the
    user's.

    Refused (ConflictError) for a user who has days or entries, and for a file referring to records it does not hold
    (checked before anything is written). On SQLite it runs in the caller's transaction, all or nothing; on DynamoDB
    it writes atomic chunks, and an import that stopped halfway (the setup is still open) is replaced by the next one.
    """
    return _Import(store, user_id, data, team_services or {}).run()


class _Import:
    def __init__(self, store: Store, user_id: str, data: UserData, team_services: dict[str, str]) -> None:
        self._store = store
        self._user = user_id
        self._data = data
        self._team_services = team_services
        self._services: dict[str, str] = {}  # file id (as text) → record id
        self._activity_types: dict[str, str] = {}
        self._entries: dict[str, str] = {}

    def run(self) -> ImportSummary:
        check_references(self._data)
        self._start()
        self._settings()
        self._services_of_file()
        self._activity_types_of_file()
        self._tickets()
        days = self._store.days(self._user)
        for day in self._data.days:
            self._store.make_room(ROOM)
            days.save(day)
        self._entries_of_file()
        self._history()
        data = self._data
        return ImportSummary(
            work_schedules=len(data.work_schedules), pto_years=len(data.pto_years), services=len(data.services),
            activity_types=len(data.activity_types), tickets=len(data.tickets), days=len(data.days),
            entries=len(data.entries), history=len(data.history),
        )

    def _start(self) -> None:
        """Only into an account without days and entries, or one whose import stopped halfway: that one goes first."""
        if self._store.import_unfinished(self._user):
            self._store.clear_records(self._user)
        elif self._has_records():
            raise ConflictError('Only an account without days and entries can import a file; this one has some')
        self._store.start_import(self._user)

    def _has_records(self) -> bool:
        return bool(self._store.days(self._user).between(dt.date.min, dt.date.max)
                    or self._store.entries(self._user).all_history())

    def _settings(self) -> None:
        self._store.save_settings(self._user, self._data.settings)
        self._store.save_theme(self._user, self._data.theme)
        if self._data.language:
            self._store.save_language(self._user, self._data.language)
        schedules = self._store.schedules(self._user)
        if self._data.work_schedules:
            first, *later = self._data.work_schedules
            schedules.replace_all(first)
            for schedule in later:
                self._store.make_room(ROOM)
                schedules.add(schedule)
        self._store.make_room(ROOM + len(self._data.pto_years))
        self._store.pto_years(self._user).replace_all(self._data.pto_years)

    def _services_of_file(self) -> None:
        """Personal services first, so a team service with the same short name uses the personal one."""
        services = self._store.services(self._user)
        by_name = {service.short_name.casefold(): service.id for service in services.all()}
        for service in sorted(self._data.services, key=lambda service: service.team is not None):
            name = service.short_name.casefold()
            if service.team is not None and name in self._team_services:
                self._services[service.id] = self._team_services[name]
                continue
            if name not in by_name:
                self._store.make_room(ROOM)
                by_name[name] = services.add(Service(short_name=service.short_name, name=service.name)).id
            self._services[service.id] = by_name[name]

    def _activity_types_of_file(self) -> None:
        """The file's activity types replace the user's (the defaults; without entries none is in use)."""
        kinds = self._store.activity_types(self._user)
        for kind in kinds.all():
            self._store.make_room(ROOM)
            kinds.delete(kind.id)
        for kind in self._data.activity_types:
            self._store.make_room(ROOM)
            self._activity_types[kind.id] = kinds.add(kind.model_copy(update={'id': None})).id

    def _tickets(self) -> None:
        tickets = self._store.tickets(self._user)
        for ticket in self._data.tickets:
            self._store.make_room(ROOM)
            tickets.ensure(ticket.key)
            if ticket.service_id is not None:
                tickets.set_service(ticket.key, self._services[ticket.service_id])

    def _entries_of_file(self) -> None:
        entries = self._store.entries(self._user)
        for entry in self._data.entries:
            update = {'id': None, 'activity_type_id': self._activity_types.get(entry.activity_type_id)}
            self._store.make_room(ROOM)
            self._entries[entry.id] = entries.restore(entry.model_copy(update=update)).id

    def _history(self) -> None:
        """Entries only in the history (deleted before the export) get reserved ids, in the order they come up."""
        entries = self._store.entries(self._user)
        for change in self._data.history:
            entry_id = self._entry_id(entries, change.entry_id)
            self._store.make_room(ROOM)
            entries.restore_history(change.model_copy(update={
                'id': None, 'entry_id': entry_id, 'changes': self._changes(change.changes),
                'detail': self._detail(entries, change),
            }))

    def _entry_id(self, entries: Entries, file_id: str) -> str:
        if file_id not in self._entries:
            self._entries[file_id] = entries.reserve_id()
        return self._entries[file_id]

    def _changes(self, changes: Changes) -> Changes:
        """Activity types named in a change by record id (None if the file does not hold them)."""
        if 'activity_type_id' not in changes:
            return changes
        old, new = changes['activity_type_id']
        return changes | {'activity_type_id': (self._activity_type(old), self._activity_type(new))}

    def _activity_type(self, file_id: object) -> str | None:
        """An activity type named in a history line (the file has its id as a number), None if it does not hold it."""
        return self._activity_types.get(str(file_id)) if file_id is not None else None

    def _detail(self, entries: Entries, change: EntryChange) -> str:
        match = SPLIT_FROM.fullmatch(change.detail) if change.action == HistoryAction.SPLIT else None
        return f'Split from entry {self._entry_id(entries, match[1])}' if match else change.detail


def check_references(data: UserData) -> None:
    """Every service and activity type the file refers to is in it (before anything is written)."""
    for references, held, label in (
        (_ids(data.tickets, 'service_id'), _ids(data.services, 'id'), 'service'),
        (_ids(data.entries, 'activity_type_id'), _ids(data.activity_types, 'id'), 'activity type'),
    ):
        _known(references, held, label)


def _ids(records: Iterable[object], field: str) -> list[str | None]:
    return [getattr(record, field) for record in records]


def _known(references: Iterable[str | None], held: Iterable[str], label: str) -> None:
    """Empty references are fine (e.g. a ticket without service)."""
    ids = set(held)
    if missing := next((file_id for file_id in references if file_id is not None and file_id not in ids), None):
        raise ConflictError(f'The file refers to {label} {missing}, which it does not hold')
