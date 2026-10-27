"""Task entries of a day: ticket entries and activity entries."""

import datetime as dt
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from src.lib.durations import MINUTES_PER_DAY, is_quarter_hour
from src.models.base import DomainModel
from src.models.catalog import TicketKey


def _check_quarter_hour(minutes: int) -> int:
    if not is_quarter_hour(minutes):
        raise ValueError('duration must be in quarter hours')
    return minutes


Duration = Annotated[
    int,
    Field(ge=0, le=MINUTES_PER_DAY, description='Minutes, in quarter hours'),
    AfterValidator(_check_quarter_hour),
]


class TicketEntry(DomainModel):
    kind: Literal['ticket'] = 'ticket'
    id: int | None = None
    date: dt.date
    ticket_key: TicketKey | None = Field(default=None, description='None only for imported entries awaiting review')
    duration: Duration
    description: str = Field(default='', max_length=1000)
    coding: bool = False


class ActivityEntry(DomainModel):
    kind: Literal['activity'] = 'activity'
    id: int | None = None
    date: dt.date
    activity_type_id: int
    duration: Duration
    note: str = Field(default='', max_length=1000)


Entry = Annotated[TicketEntry | ActivityEntry, Field(discriminator='kind')]
