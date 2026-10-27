"""Review flags set during import, on an entry or a day.

Other review reasons (ticket without service, 0:00 duration, entry without ticket) are derived
from the data and not stored as flags.
"""

import datetime as dt
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from src.models.base import DomainModel


class FlagReason(StrEnum):
    UNCERTAIN_TICKET = 'uncertain_ticket'  # e.g. '#4138' → TNG-4138, '#4347 aka #1482', 'TNG-2035ff'
    WEEKEND_HOURS = 'weekend_hours'  # weekend hours or entries the spreadsheet did not count


class ReviewFlag(DomainModel):
    id: int | None = None
    entry_id: int | None = None
    date: dt.date | None = Field(default=None, description='Set for flags on a day')
    reason: FlagReason
    detail: str = Field(default='', max_length=500, description='e.g. the original spreadsheet text')

    @model_validator(mode='after')
    def check_target(self) -> Self:
        if (self.entry_id is None) == (self.date is None):
            raise ValueError('a flag belongs to either an entry or a day')
        return self
