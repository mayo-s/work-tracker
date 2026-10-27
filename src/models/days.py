"""A recorded day: day type, working times and note."""

import datetime as dt
from typing import Annotated, Self

from pydantic import Field, model_validator

from src.lib.balances import DayRecord
from src.lib.daytypes import DayType
from src.lib.durations import MINUTES_PER_DAY
from src.lib.worktime import worked_time
from src.models.base import DomainModel

ClockTime = Annotated[int, Field(ge=0, lt=MINUTES_PER_DAY, description='Minutes since midnight')]


class Day(DomainModel):
    date: dt.date
    day_type: DayType | None = Field(default=None, description='None: automatic (work or holiday)')
    start: ClockTime | None = None
    end: ClockTime | None = None
    break_minutes: int | None = Field(default=None, ge=0, description='None: legal minimum break')
    note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def check_times(self) -> Self:
        if (self.start is None) != (self.end is None):
            raise ValueError('start and end must be set together')
        if self.start is None and self.break_minutes is not None:
            raise ValueError('a break needs start and end')
        if self.start is not None:
            worked_time(self.start, self.end, self.break_minutes)  # rejects end before start and too long breaks
        return self

    @property
    def worked(self) -> int:
        if self.start is None:
            return 0
        return worked_time(self.start, self.end, self.break_minutes)

    def to_record(self) -> DayRecord:
        return DayRecord(self.worked, self.day_type)
