"""Task entries of a day: an activity, optionally on a ticket (SPEC 4)."""

import datetime as dt
from typing import Annotated

from pydantic import Field

from src.lib.durations import MINUTES_PER_DAY
from src.models.base import DomainModel, RecordId
from src.models.catalog import TicketKey

Duration = Annotated[int, Field(ge=0, le=MINUTES_PER_DAY, description='Minutes')]


class Entry(DomainModel):
    id: RecordId | None = None
    date: dt.date
    activity_type_id: RecordId | None = Field(
        default=None, description='None only for former entries awaiting review (SPEC 4.6)')
    ticket_key: TicketKey | None = Field(default=None, description='Required by some activity types, e.g. Coding')
    duration: Duration
    description: str = Field(default='', max_length=1000)
