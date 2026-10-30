"""API schemas for task entries and their history (formats: see src.utils.api)."""

import datetime as dt
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from src.lib.durations import format_duration, parse_duration
from src.models.catalog import TicketKey
from src.models.entries import ActivityEntry, Entry, TicketEntry
from src.models.history import HistoryAction
from src.models.review import FlagReason
from src.modules.storage.catalog import ActivityTypeRepository, ServiceRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.tickets import TicketRepository
from src.utils.api import DurationText, check_domain


class EntryInput(BaseModel):
    """A ticket entry (ticket_key, description, coding) or an activity entry (activity_type_id, note)."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    kind: Literal['ticket', 'activity']
    date: dt.date
    duration: DurationText = Field(description='In quarter hours, e.g. 1:30, 1.5, 1,5, 1h30m or 90m; answered as h:mm')
    ticket_key: str | None = Field(default=None, examples=['ENGINE-461'])
    service_id: int | None = Field(
        default=None, description="Ticket entries: set the ticket's service (applies to all its entries); omit to keep it"
    )
    description: str = ''
    coding: bool = False
    activity_type_id: int | None = None
    note: str = ''

    @model_validator(mode='after')
    def check_kind(self) -> Self:
        if self.kind == 'ticket':
            self._check_ticket_entry()
        else:
            self._check_activity_entry()
        check_domain(self.to_entry)
        return self

    def _check_ticket_entry(self) -> None:
        if not self.ticket_key:
            raise ValueError('a ticket entry needs a ticket_key')
        if self.activity_type_id is not None or self.note:
            raise ValueError('a ticket entry has no activity_type_id or note')

    def _check_activity_entry(self) -> None:
        if self.activity_type_id is None:
            raise ValueError('an activity entry needs an activity_type_id')
        if self.ticket_key or 'service_id' in self.model_fields_set or self.description or self.coding:
            raise ValueError('an activity entry has no ticket_key, service_id, description or coding')

    @property
    def sets_service(self) -> bool:
        return self.kind == 'ticket' and 'service_id' in self.model_fields_set

    def to_entry(self, entry_id: int | None = None) -> Entry:
        common = {'id': entry_id, 'date': self.date, 'duration': parse_duration(self.duration)}
        if self.kind == 'ticket':
            return TicketEntry(**common, ticket_key=self.ticket_key, description=self.description, coding=self.coding)
        return ActivityEntry(**common, activity_type_id=self.activity_type_id, note=self.note)


class EntrySplitInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    ticket_keys: list[TicketKey] = Field(min_length=2, examples=[['TNG-4347', 'KP-1482']],
                                         description='The entry keeps the first ticket; the hours are split evenly')


class EntryFlagView(BaseModel):
    id: int
    reason: FlagReason
    detail: str


class EntryView(BaseModel):
    id: int
    kind: Literal['ticket', 'activity']
    date: dt.date
    duration: str
    ticket_key: str | None = None
    service_id: int | None = None
    service: str | None = Field(default=None, description="Short name of the ticket's service")
    description: str | None = None
    coding: bool = False
    activity_type_id: int | None = None
    activity_type: str | None = None
    note: str | None = None
    changed: bool = Field(description='Changed after it was created or imported (see its history)')
    flags: list[EntryFlagView]


class ChangeView(BaseModel):
    id: int
    changed_at: dt.datetime
    action: HistoryAction
    changes: dict[str, tuple[JsonValue, JsonValue]] = Field(description='Changed fields: [old, new]; durations in minutes')
    detail: str


class EntryViewer:
    """Builds entry views with service, activity type, flags and the changed marker (one lookup per list)."""

    def __init__(self, conn: sqlite3.Connection, user_id: str) -> None:
        self._entries = EntryRepository(conn, user_id)
        self._ticket_services = {ticket.key: ticket.service_id for ticket in TicketRepository(conn, user_id).all()}
        self._services = {service.id: service.short_name for service in ServiceRepository(conn, user_id).choices()}
        self._activity_types = {activity.id: activity.name for activity in ActivityTypeRepository(conn, user_id).all()}

    def views(self, entries: Iterable[Entry]) -> list[EntryView]:
        entries = list(entries)
        changed = self._entries.changed(entry.id for entry in entries)
        flags = defaultdict(list)
        for flag in self._entries.entry_flags():
            flags[flag.entry_id].append(EntryFlagView(id=flag.id, reason=flag.reason, detail=flag.detail))
        return [self._view(entry, entry.id in changed, flags[entry.id]) for entry in entries]

    def view(self, entry: Entry) -> EntryView:
        return self.views([entry])[0]

    def _view(self, entry: Entry, changed: bool, flags: list[EntryFlagView]) -> EntryView:
        common = {
            'id': entry.id, 'kind': entry.kind, 'date': entry.date, 'duration': format_duration(entry.duration),
            'changed': changed, 'flags': flags,
        }
        if isinstance(entry, TicketEntry):
            service_id = self._ticket_services.get(entry.ticket_key)
            return EntryView(
                **common, ticket_key=entry.ticket_key, service_id=service_id, service=self._services.get(service_id),
                description=entry.description, coding=entry.coding,
            )
        return EntryView(
            **common, activity_type_id=entry.activity_type_id,
            activity_type=self._activity_types.get(entry.activity_type_id), note=entry.note,
        )
