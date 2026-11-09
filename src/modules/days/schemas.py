"""API schemas for days (formats: see src.utils.api)."""

import datetime as dt
from collections.abc import Callable
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.lib.daytypes import DayType, summarize_day
from src.lib.durations import format_clock, format_duration, parse_clock, parse_duration
from src.lib.public_holidays import holiday_on
from src.lib.schedules import STANDARD, WorkSchedule
from src.lib.stays import Stays
from src.lib.worktime import best_end, legal_break
from src.models.days import Day
from src.utils.api import ClockText, DurationText, check_domain

_WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


class DayInput(BaseModel):
    """A recorded day; without break_time the legal minimum break applies."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    day_type: DayType | None = Field(default=None, description='Empty: automatic (work day or holiday)')
    start: ClockText | None = None
    end: ClockText | None = None
    break_time: DurationText | None = Field(default=None, description='Empty: legal minimum break')
    note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def check_day(self) -> Self:
        """An end or a break only with a start, end after start, break not longer than presence."""
        check_domain(lambda: self.to_day(dt.date.min))
        return self

    def to_day(self, date: dt.date) -> Day:
        return Day(
            date=date,
            day_type=self.day_type,
            start=_minutes(self.start, parse_clock),
            end=_minutes(self.end, parse_clock),
            break_minutes=_minutes(self.break_time, parse_duration),
            note=self.note,
        )


class DayView(BaseModel):
    """A calendar day with its effective day type, times and balance, whether recorded or not."""

    date: dt.date
    weekday: str = Field(examples=['Mon'])
    day_type: DayType = Field(description='Effective day type: the chosen one, or automatic')
    automatic: bool = Field(description='True if no day type was chosen')
    holiday: str | None = Field(description='Name of the public holiday or company half day')
    recorded: bool
    start: str | None
    end: str | None = Field(description='Empty with a start: the day is open and counts as nothing worked yet')
    best_end: str | None = Field(description='An open day: the end that meets the target, without overtime or loss')
    break_time: str | None = Field(description='Effective break, h:mm')
    break_default: bool = Field(description='True if the break is the legal minimum')
    worked: str
    target: str
    overtime: str
    pto_days: float
    work_day: bool = Field(description='A work day of the work schedule, e.g. Monday to Friday')
    note: str
    in_team: bool = Field(default=True,
                          description='Team view: false for days before the member joined the team, shown without data')


def day_view(date: dt.date, day: Day | None, schedule: WorkSchedule = STANDARD) -> DayView:
    record = day or Day(date=date)
    summary = summarize_day(date, record.worked, record.day_type, schedule)
    holiday = holiday_on(date, schedule.holidays)
    return DayView(
        date=date,
        weekday=_WEEKDAYS[date.weekday()],
        day_type=summary.day_type,
        automatic=record.day_type is None,
        holiday=holiday.name if holiday else None,
        recorded=day is not None,
        start=_text(record.start, format_clock),
        end=_text(record.end, format_clock),
        best_end=_text(best_end(record.start, summary.target, record.break_minutes) if record.is_open else None, format_clock),
        break_time=_text(_effective_break(record), format_duration),
        break_default=record.end is not None and record.break_minutes is None,
        worked=format_duration(summary.worked),
        target=format_duration(summary.target),
        overtime=format_duration(summary.overtime),
        pto_days=float(summary.pto_days),
        work_day=summary.work_day,
        note=record.note,
    )


def _effective_break(day: Day) -> int | None:
    if day.end is None:
        return day.break_minutes  # an open day has only the one entered
    return day.break_minutes if day.break_minutes is not None else legal_break(day.end - day.start)


def _minutes(text: str | None, parse: Callable[[str], int]) -> int | None:
    return None if text is None else parse(text)


def _text(minutes: int | None, format_: Callable[[int], str]) -> str | None:
    return None if minutes is None else format_(minutes)


def team_view_day(day: DayView, stays: Stays) -> DayView:
    """A member's day in the team view: no note; a day not in the team (before they joined, after
    they left, between stays) without any data."""
    if stays.shows(day.date):
        return day.model_copy(update={'note': ''})
    empty = {'recorded': False, 'start': None, 'end': None, 'best_end': None, 'break_time': None, 'break_default': False,
             'worked': '0:00', 'target': '0:00', 'overtime': '0:00', 'pto_days': 0.0, 'note': '', 'in_team': False}
    return day.model_copy(update=empty)
