"""The export file of a user's own data (SPEC 5.8): one JSON document, version 2 (version 1 is read too).

It reuses the domain models. Every record has a file id (1, 2, …), and references (a ticket's service, an entry's
activity type, a history line's or flag's entry) use these ids, not those of the database. Version 1 held ticket and
activity entries; reading converts them to entries of one kind (SPEC 4.6).
"""

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.models.base import DomainModel
from src.models.catalog import ActivityType, ServiceChoice, Ticket
from src.models.days import Day
from src.models.catalog import new_activity_type
from src.models.entries import Entry
from src.models.former_entries import convert
from src.models.history import EntryChange
from src.models.pto import PtoYear
from src.models.review import ReviewFlag
from src.models.schedules import Schedule
from src.models.settings import Settings
from src.modules.storage.store import Theme

FORMAT = 'work-tracker'
VERSION = 2


class UserData(DomainModel):
    format: Literal['work-tracker']
    version: int = Field(ge=1, le=VERSION, description='Format version; a newer one cannot be imported')
    exported_at: dt.datetime
    settings: Settings
    theme: Theme
    work_schedules: list[Schedule]
    pto_years: list[PtoYear]
    services: list[ServiceChoice] = Field(description='Personal services, and team services (`team`) the tickets use')
    activity_types: list[ActivityType]
    tickets: list[Ticket]
    days: list[Day]
    entries: list[Entry]
    history: list[EntryChange] = Field(description='All history lines, also of deleted entries, in written order')
    review_flags: list[ReviewFlag]

    @model_validator(mode='before')
    @classmethod
    def known_format(cls, data: Any) -> Any:
        """Another format or a newer version is refused before the contents are checked."""
        if isinstance(data, dict):
            _check_format(data.get('format'), data.get('version'))
            if data.get('version') == 1:
                return _from_version_1(data)
        return data


def _from_version_1(data: dict[str, Any]) -> dict[str, Any]:
    """The file with entries of one kind; an activity type they need (Coding, Meeting) is added to the file's."""
    activity_types = _FileActivityTypes(data.get('activity_types', []))
    entries = [convert(entry, activity_types) if isinstance(entry, dict) and 'kind' in entry else entry
               for entry in data.get('entries', [])]
    return data | {'activity_types': activity_types.records, 'entries': entries}


class _FileActivityTypes:
    """The activity types of a file; called with a name, the file id of that type, added with the next id if needed."""

    def __init__(self, records: list[Any]) -> None:
        self.records = [dict(record) for record in records if isinstance(record, dict)]
        self._ids = {str(record.get('name', '')).casefold(): str(record.get('id')) for record in self.records}

    def __call__(self, name: str) -> str:
        if name.casefold() not in self._ids:
            self._ids[name.casefold()] = _next_id(self.records)
            self.records.append(new_activity_type(name).model_dump() | {'id': self._ids[name.casefold()]})
        return self._ids[name.casefold()]


def _next_id(records: list[dict[str, Any]]) -> str:
    """The file id after the highest one."""
    return str(1 + max((int(record['id']) for record in records if str(record.get('id')).isdigit()), default=0))


def _check_format(name: Any, version: Any) -> None:
    if name != FORMAT:
        raise ValueError('This is no Work Tracker export file')
    if isinstance(version, int) and version > VERSION:
        raise ValueError(f'The file has version {version}; this Work Tracker reads up to version {VERSION}')


class ImportSummary(BaseModel):
    """How many records of each type an import wrote."""

    work_schedules: int
    pto_years: int
    services: int
    activity_types: int
    tickets: int
    days: int
    entries: int
    history: int
    review_flags: int
