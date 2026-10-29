"""Booking a full-day type (e.g. PTO) on the work days of a date range, in one transaction.

Only work days of the schedule get the type; days off of the schedule (e.g. weekends), public holidays and
company half days are left out. Work days that already hold times or entries are conflicts: they are refused,
skipped or booked too (keeping their times and entries).
"""

import datetime as dt
import sqlite3
from collections import Counter
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.lib.dates import each_day
from src.lib.daytypes import DayType, summarize_day
from src.lib.durations import format_duration
from src.lib.public_holidays import HolidayKind, holiday_on
from src.lib.schedules import WEEKDAYS, Schedules
from src.models.days import Day
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.errors import ConflictError
from src.modules.storage.schedules import ScheduleRepository
from src.utils.api import MAX_DAYS

RangeDayType = Literal[DayType.PTO, DayType.SICK, DayType.UNPAID_LEAVE, DayType.OVERTIME_OFF]


class DayRangeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    start: dt.date
    end: dt.date
    day_type: RangeDayType = Field(description='A full-day type: pto, sick, unpaid_leave or overtime_off')
    note: str = Field(default='', max_length=500, description='Note for days without a note of their own')
    conflicts: Literal['refuse', 'skip', 'include'] = Field(
        default='refuse',
        description='Work days holding times or entries: refuse the range (409), skip them, or book them too',
    )
    preview: bool = Field(default=False, description='Only show what would be booked, save nothing')

    @model_validator(mode='after')
    def check_range(self) -> Self:
        if not 0 <= (self.end - self.start).days < MAX_DAYS:
            raise ValueError(f'end must be on or after start, at most {MAX_DAYS} days')
        return self


class RecordedDay(BaseModel):
    date: dt.date
    weekday: str
    worked: str
    entries: int


class LeftOutDay(BaseModel):
    date: dt.date
    weekday: str
    reason: Literal['day_off', 'public_holiday', 'company_half_day']
    holiday: str | None = Field(description='Name of the public holiday or company half day')


class DayRangeResult(BaseModel):
    saved: bool
    days: list[dt.date] = Field(description='Work days that get (or got) the day type')
    conflicts: list[RecordedDay] = Field(description='Work days holding times or entries; booked only with conflicts=include')
    left_out: list[LeftOutDay] = Field(description='Days off of the schedule, public holidays and company half days')
    pto_days: float = Field(description='PTO the booked days use')


class _Plan:
    """The days of the range sorted into free work days, conflicts and days left out."""

    def __init__(self, conn: sqlite3.Connection, user_id: str, data: DayRangeInput) -> None:
        self.schedules: Schedules = ScheduleRepository(conn, user_id).schedules()
        self.recorded = {day.date: day for day in DayRepository(conn, user_id).between(data.start, data.end)}
        self.entries = Counter(entry.date for entry in EntryRepository(conn, user_id).between(data.start, data.end))
        self.free: list[dt.date] = []
        self.conflicts: list[RecordedDay] = []
        self.left_out: list[LeftOutDay] = []
        for date in each_day(data.start, data.end):
            self._sort(date)

    def _sort(self, date: dt.date) -> None:
        if left_out := self._left_out(date):
            self.left_out.append(left_out)
        elif self._has_data(date):
            worked = self.recorded[date].worked if date in self.recorded else 0
            self.conflicts.append(RecordedDay(date=date, weekday=_weekday(date), worked=format_duration(worked),
                                              entries=self.entries[date]))
        else:
            self.free.append(date)

    def _left_out(self, date: dt.date) -> LeftOutDay | None:
        """A day off of the schedule, a public holiday or a company half day; None for a work day."""
        schedule = self.schedules.on(date)
        holiday = holiday_on(date, schedule.holidays)
        if schedule.is_work_day(date) and not holiday:
            return None
        reason = _HOLIDAY_REASONS[holiday.kind] if holiday and schedule.is_work_day(date) else 'day_off'
        return LeftOutDay(date=date, weekday=_weekday(date), reason=reason, holiday=holiday.name if holiday else None)

    def _has_data(self, date: dt.date) -> bool:
        day = self.recorded.get(date)
        return bool(self.entries[date]) or (day is not None and day.start is not None)

    def booked(self, conflicts: str) -> list[dt.date]:
        return sorted(self.free + ([day.date for day in self.conflicts] if conflicts == 'include' else []))

    def check(self, data: DayRangeInput) -> None:
        """Refused conflicts stop the booking (a preview only lists them)."""
        if self.conflicts and data.conflicts == 'refuse' and not data.preview:
            dates = ', '.join(f'{day.date:%d.%m.%Y}' for day in self.conflicts)
            raise ConflictError(f'{len(self.conflicts)} days hold times or entries: {dates}')

    def pto_days(self, booked: list[dt.date], day_type: DayType) -> float:
        return float(sum(summarize_day(date, 0, day_type, self.schedules.on(date)).pto_days for date in booked))


_HOLIDAY_REASONS = {HolidayKind.PUBLIC: 'public_holiday', HolidayKind.COMPANY_HALF_DAY: 'company_half_day'}


def _weekday(date: dt.date) -> str:
    return WEEKDAYS[date.weekday()]


def book_range(conn: sqlite3.Connection, user_id: str, data: DayRangeInput) -> DayRangeResult:
    """Book the day type on the work days of the range, or only preview it; refused conflicts raise a ConflictError."""
    plan = _Plan(conn, user_id, data)
    plan.check(data)
    booked = plan.booked(data.conflicts)
    if not data.preview:
        _save(DayRepository(conn, user_id), plan, booked, data)
    return DayRangeResult(saved=not data.preview, days=booked, conflicts=plan.conflicts, left_out=plan.left_out,
                          pto_days=plan.pto_days(booked, data.day_type))


def _save(days: DayRepository, plan: _Plan, booked: list[dt.date], data: DayRangeInput) -> None:
    """The type on each booked day; recorded days keep their times and note (the range's note fills an empty one)."""
    for date in booked:
        day = plan.recorded.get(date) or Day(date=date)
        days.save(day.model_copy(update={'day_type': data.day_type, 'note': day.note or data.note}))
