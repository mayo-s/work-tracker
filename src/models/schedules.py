"""Work schedules: hours per week on chosen work days and the holiday rules, valid from a date."""

import datetime as dt
from typing import Annotated

from pydantic import Field, field_validator

from src.lib.public_holidays import STATES, HolidayRules
from src.lib.schedules import MINUTES_PER_WEEK, WorkSchedule
from src.models.base import DomainModel

IsoWeekday = Annotated[int, Field(ge=1, le=7)]


class Schedule(DomainModel):
    id: int | None = None
    valid_from: dt.date = Field(description='First day the schedule applies to')
    weekly_minutes: int = Field(ge=0, le=MINUTES_PER_WEEK)
    work_days: list[IsoWeekday] = Field(min_length=1, description='ISO weekdays: 1 = Monday … 7 = Sunday')
    state: str = Field(default='BE', description='German federal state whose public holidays apply, e.g. BE')
    company_half_days: bool = Field(default=True, description='24.12. and 31.12. are half PTO, half free')

    @field_validator('state')
    @classmethod
    def known_state(cls, state: str) -> str:
        if state not in STATES:
            raise ValueError(f'Unknown federal state {state!r}')
        return state

    @field_validator('work_days')
    @classmethod
    def sorted_and_distinct(cls, days: list[int]) -> list[int]:
        return sorted(set(days))

    def to_work_schedule(self) -> WorkSchedule:
        holidays = HolidayRules(self.state, self.company_half_days)
        return WorkSchedule(self.valid_from, self.weekly_minutes, frozenset(self.work_days), holidays)
