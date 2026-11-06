"""API schemas for task entries and their history (formats: see src.utils.api)."""

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from src.lib.durations import format_duration, parse_duration
from src.models.catalog import TicketKey
from src.models.entries import Entry
from src.models.history import HistoryAction
from src.models.review import FlagReason
from src.modules.storage.store import Store
from src.modules.tickets.schemas import TicketServices
from src.utils.api import DurationText, check_domain


class EntryInput(BaseModel):
    """An activity, optionally on a ticket (SPEC 4)."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    date: dt.date
    activity_type_id: str = Field(description='One of the user\'s activity types; some require a ticket (e.g. Coding)')
    duration: DurationText = Field(description='In quarter hours, e.g. 1:30, 1.5, 1,5, 1h30m or 90m; answered as h:mm')
    ticket_key: str | None = Field(default=None, examples=['ENGINE-461'])
    service_id: str | None = Field(
        default=None, description="With a ticket: set the ticket's service (applies to all its entries); omit to keep it"
    )
    description: str = ''

    @model_validator(mode='after')
    def check_entry(self) -> Self:
        if 'service_id' in self.model_fields_set and not self.ticket_key:
            raise ValueError('a service is set on a ticket: service_id needs a ticket_key')
        check_domain(self.to_entry)
        return self

    @property
    def sets_service(self) -> bool:
        return 'service_id' in self.model_fields_set

    def to_entry(self, entry_id: str | None = None) -> Entry:
        return Entry(id=entry_id, date=self.date, activity_type_id=self.activity_type_id, ticket_key=self.ticket_key or None,
                     duration=parse_duration(self.duration), description=self.description)


class EntrySplitInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    ticket_keys: list[TicketKey] = Field(min_length=2, examples=[['TNG-4347', 'KP-1482']],
                                         description='The entry keeps the first ticket; the hours are split evenly')


class EntryFlagView(BaseModel):
    id: str
    reason: FlagReason
    detail: str


class EntryView(BaseModel):
    id: str
    date: dt.date
    duration: str
    activity_type_id: str | None = Field(description='None only for former entries awaiting review')
    activity_type: str | None
    ticket_required: bool = Field(description='Its activity type requires a ticket')
    ticket_key: str | None
    service_id: str | None
    service: str | None = Field(description="Short name of the ticket's service")
    description: str
    changed: bool = Field(description='Changed after it was created or imported (see its history)')
    flags: list[EntryFlagView]


class ChangeView(BaseModel):
    id: str
    changed_at: dt.datetime
    action: HistoryAction
    changes: dict[str, tuple[JsonValue, JsonValue]] = Field(description='Changed fields: [old, new]; durations in minutes')
    detail: str


class EntryViewer:
    """Builds entry views with service, activity type, flags and the changed marker (one lookup per list)."""

    def __init__(self, store: Store, user_id: str) -> None:
        self._entries = store.entries(user_id)
        self._services = TicketServices(store, user_id)
        self._activity_types = {activity.id: activity for activity in store.activity_types(user_id).all()}

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
        activity_type = self._activity_types.get(entry.activity_type_id)
        service_id = self._services.of_ticket(entry.ticket_key)
        return EntryView(
            id=entry.id, date=entry.date, duration=format_duration(entry.duration), activity_type_id=entry.activity_type_id,
            activity_type=activity_type.name if activity_type else None,
            ticket_required=bool(activity_type and activity_type.ticket_required), ticket_key=entry.ticket_key,
            service_id=service_id, service=self._services.name(service_id), description=entry.description,
            changed=changed, flags=flags,
        )
