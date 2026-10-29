"""Work schedules as shown and entered in the API: hours per week as h:mm, work days as weekday names."""

import datetime as dt
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.lib.durations import format_duration, parse_duration
from src.lib.public_holidays import STATES
from src.lib.schedules import WEEKDAYS
from src.models.schedules import Schedule
from src.utils.api import DurationText, check_domain

Weekday = Literal['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
State = Literal[STATES]


class ScheduleTerms(BaseModel):
    """A work schedule without its start date."""

    model_config = ConfigDict(extra='forbid')

    weekly_hours: DurationText = Field(description='Hours per week, h:mm', examples=['40:00'])
    work_days: list[Weekday] = Field(min_length=1, examples=[['Mon', 'Tue', 'Wed', 'Thu', 'Fri']])
    state: State = Field(default='BE', description='German federal state whose public holidays apply')
    company_half_days: bool = Field(default=True, description='24.12. and 31.12. are half PTO, half free')

    def starting(self, start: dt.date) -> 'ScheduleInput':
        return ScheduleInput(valid_from=start, **self.model_dump())


class ScheduleInput(ScheduleTerms):
    valid_from: dt.date = Field(description='First day the schedule applies to; earlier days keep their schedule')

    @model_validator(mode='after')
    def check_schedule(self) -> Self:
        check_domain(self.to_schedule)
        return self

    def to_schedule(self, schedule_id: int | None = None) -> Schedule:
        return Schedule(
            id=schedule_id, valid_from=self.valid_from, weekly_minutes=parse_duration(self.weekly_hours),
            work_days=[WEEKDAYS.index(day) + 1 for day in self.work_days], state=self.state,
            company_half_days=self.company_half_days,
        )


class ScheduleView(ScheduleInput):
    id: int
    daily_target: str = Field(description='Hours per week split evenly over the work days, h:mm', examples=['8:00'])

    @classmethod
    def of(cls, schedule: Schedule) -> Self:
        return cls(
            id=schedule.id, valid_from=schedule.valid_from, weekly_hours=format_duration(schedule.weekly_minutes),
            work_days=[WEEKDAYS[day - 1] for day in schedule.work_days], state=schedule.state,
            company_half_days=schedule.company_half_days,
            daily_target=format_duration(schedule.to_work_schedule().daily_target),
        )
