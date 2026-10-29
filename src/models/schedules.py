"""Work schedules: hours per week on chosen work days, valid from a date."""

import datetime as dt
from typing import Annotated

from pydantic import Field, field_validator

from src.lib.schedules import MINUTES_PER_WEEK, WorkSchedule
from src.models.base import DomainModel

IsoWeekday = Annotated[int, Field(ge=1, le=7)]


class Schedule(DomainModel):
    id: int | None = None
    valid_from: dt.date = Field(description='First day the schedule applies to')
    weekly_minutes: int = Field(ge=0, le=MINUTES_PER_WEEK)
    work_days: list[IsoWeekday] = Field(min_length=1, description='ISO weekdays: 1 = Monday … 7 = Sunday')

    @field_validator('work_days')
    @classmethod
    def sorted_and_distinct(cls, days: list[int]) -> list[int]:
        return sorted(set(days))

    def to_work_schedule(self) -> WorkSchedule:
        return WorkSchedule(self.valid_from, self.weekly_minutes, frozenset(self.work_days))
