"""The export file of a user's own data (SPEC 5.8): one JSON document, version 1.

It reuses the domain models. Every record has a file id (1, 2, …), and references (a ticket's service, an activity
entry's type, a history line's or flag's entry) use these ids, not those of the database.
"""

import datetime as dt
from typing import Literal

from pydantic import Field

from src.models.base import DomainModel
from src.models.catalog import ActivityType, ServiceChoice, Ticket
from src.models.days import Day
from src.models.entries import Entry
from src.models.history import EntryChange
from src.models.pto import PtoYear
from src.models.review import ReviewFlag
from src.models.schedules import Schedule
from src.models.settings import Settings
from src.modules.storage.store import Theme

FORMAT = 'work-tracker'
VERSION = 1


class UserData(DomainModel):
    format: Literal['work-tracker'] = FORMAT
    version: int = Field(default=VERSION, description='Format version; a newer one cannot be imported')
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
