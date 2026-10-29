"""The dashboard (start page): key figures, the overtime balance over time, the days off coming up and this year's figures.

Everything counts up to today, like the reports; "coming up" looks at the next 60 days. In the team view, the balance
over time and this week's and this year's figures start on the day the member joined the team; the balance and the PTO
account are running figures.
"""

import datetime as dt
import sqlite3
from itertools import accumulate

from pydantic import BaseModel, Field

from src.lib.balances import summarize_period
from src.lib.daytypes import DaySummary, DayType
from src.lib.durations import format_duration, parse_duration
from src.lib.public_holidays import holiday_on
from src.modules.reports.schemas import CodingWork, PeriodTotals, PtoView, Reports, VisibleFrom
from src.modules.review.schemas import review
from src.modules.storage.days import DayRepository
from src.modules.storage.schedules import ScheduleRepository
from src.modules.storage.settings import load_settings

COMING_UP_DAYS = 60
_HOLIDAYS = {DayType.PUBLIC_HOLIDAY, DayType.COMPANY_HALF_DAY}
_PLANNED = {DayType.PTO, DayType.PTO_HALF, DayType.SICK, DayType.SICK_HALF, DayType.UNPAID_LEAVE, DayType.OVERTIME_OFF}


class BalancePoint(BaseModel):
    date: dt.date
    minutes: int = Field(description='Overtime balance at the end of the day, in minutes')
    balance: str = Field(description='The same as h:mm')


class BalanceSeries(BaseModel):
    """The overtime balance over time; months end with their last day (the current one with today)."""

    month: list[BalancePoint] = Field(description='Each day of the current month up to today')
    year: list[BalancePoint] = Field(description='The end of each month of the current year')
    last_12_months: list[BalancePoint] = Field(description='The end of each of the last 12 months')
    all: list[BalancePoint] = Field(description='The end of each month since the balance start')


class ComingUp(BaseModel):
    start: dt.date
    end: dt.date
    day_type: DayType
    holiday: str | None = Field(description='Name of the public holiday or company half day')
    days: int = Field(description='Work days from start to end')


class ServiceHours(BaseModel):
    service: str | None = Field(description='Short name; null for tickets without service')
    duration: str


class YearFigures(BaseModel):
    year: int
    days_worked: int
    average_per_day_worked: str
    sick_days: float = Field(description='Full sick days, half days count half')
    overtime_off_days: int
    coding: str = Field(description='Coding hours of the year')
    top_services: list[ServiceHours] = Field(description='The three services with the most coding hours')


class DashboardView(BaseModel):
    today: dt.date
    balance: str = Field(description='Overtime balance today')
    balance_change_this_year: str = Field(description='Change since the end of last year (or the balance start)')
    pto: PtoView | None = Field(description="This year's PTO account; null without PTO days entered")
    week: str = Field(examples=['2026-W44'])
    this_week: PeriodTotals = Field(description='Worked, target and overtime of this week up to today')
    week_target: str = Field(description="The whole week's target under the work schedule, planned days off included")
    review_open: int = Field(description='Open items on the review page')
    balance_series: BalanceSeries
    coming_up: list[ComingUp] = Field(description=f'Public holidays, company half days and planned days off in the next '
                                                  f'{COMING_UP_DAYS} days; days in a row combined')
    this_year: YearFigures
    visible_from: VisibleFrom = None


class Dashboard:
    """Builds the dashboard within the transaction of the given connection."""

    def __init__(self, conn: sqlite3.Connection, user_id: str, today: dt.date, visible_from: dt.date | None = None) -> None:
        self._conn = conn
        self._user = user_id
        self._today = today
        self._visible_from = visible_from
        self._settings = load_settings(conn, user_id)
        self._first = max(self._settings.balance_start, visible_from or dt.date.min)
        self._schedules = ScheduleRepository(conn, user_id).schedules()
        last = today + dt.timedelta(days=COMING_UP_DAYS)
        self._records = DayRepository(conn, user_id).records(self._settings.balance_start, last)
        self._reports = Reports(conn, user_id, today, visible_from)
        self._balances = self._daily_balances()

    def view(self) -> DashboardView:
        iso_year, iso_week, _ = self._today.isocalendar()
        week = f'{iso_year}-W{iso_week:02d}'
        monday = self._today - dt.timedelta(days=self._today.weekday())
        year = self._reports.year(self._today.year)
        return DashboardView(
            today=self._today,
            balance=format_duration(self._balance_on(self._today)),
            balance_change_this_year=format_duration(
                self._balance_on(self._today) - self._balance_on(dt.date(self._today.year - 1, 12, 31))),
            pto=year.pto,
            week=week,
            this_week=self._reports.week(week, monday).totals,
            week_target=format_duration(sum(day.target for day in self._summaries(max(monday, self._first),
                                                                                  monday + dt.timedelta(days=6)))),
            review_open=0 if self._visible_from else sum(review(self._conn, self._user).counts.model_dump().values()),
            balance_series=self._series(),
            coming_up=self._coming_up(),
            this_year=self._year_figures(year.days_worked, year.average_per_day_worked, year.days_off),
            visible_from=self._visible_from,
        )

    def _daily_balances(self) -> dict[dt.date, int]:
        """The balance at the end of each day from the balance start up to today."""
        days = self._summaries(self._settings.balance_start, self._today)
        totals = accumulate((day.overtime for day in days), initial=self._settings.opening_balance)
        return dict(zip((day.date for day in days), list(totals)[1:]))

    def _summaries(self, start: dt.date, end: dt.date) -> list[DaySummary]:
        return summarize_period(self._records, start, end, self._schedules) if start <= end else []

    def _balance_on(self, date: dt.date) -> int:
        """The balance at the end of the day; before the balance start, the opening balance."""
        return self._balances.get(date, self._settings.opening_balance if date < self._settings.balance_start else 0)

    def _series(self) -> BalanceSeries:
        start, today = self._first, self._today
        month_start = max(start, today.replace(day=1))
        return BalanceSeries(
            month=[self._point(day.date) for day in self._summaries(month_start, today)],
            year=self._month_ends(max(start, dt.date(today.year, 1, 1))),
            last_12_months=self._month_ends(max(start, _months_back(today, 11))),
            all=self._month_ends(start),
        )

    def _month_ends(self, first: dt.date) -> list[BalancePoint]:
        """The balance at the end of each month from the month of `first` up to today (the current month: today)."""
        points, month = [], first.replace(day=1)
        while month <= self._today:
            points.append(self._point(min(_months_back(month, -1) - dt.timedelta(days=1), self._today)))
            month = _months_back(month, -1)
        return points

    def _point(self, date: dt.date) -> BalancePoint:
        minutes = self._balance_on(date)
        return BalancePoint(date=date, minutes=minutes, balance=format_duration(minutes))

    def _coming_up(self) -> list[ComingUp]:
        items: list[ComingUp] = []
        tomorrow = self._today + dt.timedelta(days=1)
        for day in self._summaries(tomorrow, self._today + dt.timedelta(days=COMING_UP_DAYS)):
            if day.work_day:
                _add_coming_up(items, day, self._holiday_name(day))
        return [item for item in items if item.day_type is not DayType.WORK]

    def _holiday_name(self, day: DaySummary) -> str | None:
        found = holiday_on(day.date, self._schedules.on(day.date).holidays) if day.day_type in _HOLIDAYS else None
        return found.name if found else None

    def _year_figures(self, days_worked: int, average: str, days_off: dict[DayType, int]) -> YearFigures:
        year = self._today.year
        first = max(dt.date(year, 1, 1), self._visible_from or dt.date.min)
        coding = CodingWork(self._conn, self._user).by_service(first, dt.date(year, 12, 31))
        top = sorted(coding, key=lambda work: parse_duration(work.duration), reverse=True)[:3]
        return YearFigures(
            year=year, days_worked=days_worked, average_per_day_worked=average,
            sick_days=days_off.get(DayType.SICK, 0) + days_off.get(DayType.SICK_HALF, 0) / 2,
            overtime_off_days=days_off.get(DayType.OVERTIME_OFF, 0),
            coding=format_duration(sum(parse_duration(work.duration) for work in coding)),
            top_services=[ServiceHours(service=work.service, duration=work.duration) for work in top],
        )


def _add_coming_up(items: list[ComingUp], day: DaySummary, holiday: str | None) -> None:
    """Adds a holiday or planned day off; a planned day continues the previous item of its type if that ended on the
    work day before (days off of the schedule in between do not count). Other work days end any run."""
    if day.day_type not in _HOLIDAYS | _PLANNED:
        items.append(ComingUp(start=day.date, end=day.date, day_type=DayType.WORK, holiday=None, days=0))  # a run breaker
        return
    last = items[-1] if items else None
    if _continues(last, day, holiday):
        items[-1] = last.model_copy(update={'end': day.date, 'days': last.days + 1})
    else:
        items.append(ComingUp(start=day.date, end=day.date, day_type=day.day_type, holiday=holiday, days=1))


def _continues(last: ComingUp | None, day: DaySummary, holiday: str | None) -> bool:
    """Planned days off of one type in a row form one item; holidays stand alone."""
    return last is not None and holiday is None and last.holiday is None and last.day_type is day.day_type


def _months_back(date: dt.date, months: int) -> dt.date:
    """The first of the month `months` before the month of `date` (negative: after)."""
    index = date.year * 12 + date.month - 1 - months
    return dt.date(index // 12, index % 12 + 1, 1)
