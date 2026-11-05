"""The dashboard (start page): key figures, the overtime balance over time, the days off coming up and this year's figures.

Everything counts up to today, like the reports; "coming up" looks at the next 60 days. In the team view, the balance
over time and this week's and this year's figures start on the day the member joined the team; the balance and the PTO
account are running figures.
"""

import datetime as dt

from pydantic import BaseModel, Field

from src.lib.balances import summarize_period
from src.lib.daytypes import DaySummary, DayType
from src.lib.durations import format_duration, parse_duration
from src.lib.public_holidays import holiday_on
from src.lib.stays import Stays
from src.modules.reports.schemas import CodingWork, PeriodTotals, PtoView, Reports, VisibleFrom
from src.modules.review.schemas import review_counts
from src.modules.storage.store import Store

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
    pto_days: float = Field(description='PTO the days use, also by themselves (0.5 for a company half day)')


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


class Dashboard(Reports):
    """Builds the dashboard within the transaction of the given store: the reports' figures of today's week and year,
    the balance over time and the days off coming up."""

    def __init__(self, store: Store, user_id: str, today: dt.date, stays: Stays | None = None) -> None:
        super().__init__(store, user_id, today, stays)
        self._ledger = self._ledger_until(max(today + dt.timedelta(days=COMING_UP_DAYS), dt.date(today.year, 12, 31)))

    def view(self) -> DashboardView:
        iso_year, iso_week, _ = self._today.isocalendar()
        week = f'{iso_year}-W{iso_week:02d}'
        monday = self._today - dt.timedelta(days=self._today.weekday())
        year = self.year(self._today.year)
        return DashboardView(
            today=self._today,
            balance=format_duration(self._ledger.balance(self._today)),
            balance_change_this_year=format_duration(
                self._ledger.balance(self._today) - self._ledger.balance(dt.date(self._today.year - 1, 12, 31))),
            pto=year.pto,
            week=week,
            this_week=self.week(week, monday).totals,
            week_target=format_duration(sum(day.target for day in self._period_days(self._ledger, monday,
                                                                                    monday + dt.timedelta(days=6)))),
            review_open=0 if self._visible_from else sum(review_counts(self._store, self._user).model_dump().values()),
            balance_series=self._series(),
            coming_up=self._coming_up(),
            this_year=self._year_figures(year.days_worked, year.average_per_day_worked, year.days_off),
            visible_from=self._visible_from,
        )

    def _series(self) -> BalanceSeries:
        start, today = self._first, self._today
        month_start = max(start, today.replace(day=1))
        return BalanceSeries(
            month=[self._point(day.date) for day in self._ledger.days(month_start, today)],
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
        minutes = self._ledger.balance(date)
        return BalancePoint(date=date, minutes=minutes, balance=format_duration(minutes))

    def _coming_up(self) -> list[ComingUp]:
        items: list[ComingUp] = []
        tomorrow = self._today + dt.timedelta(days=1)
        days = summarize_period(self._records, tomorrow, self._today + dt.timedelta(days=COMING_UP_DAYS), self._schedules)
        for day in self._only_shown(days):
            if day.work_day:
                _add_coming_up(items, day, self._holiday_name(day))
        return [item for item in items if item.day_type is not DayType.WORK]

    def _holiday_name(self, day: DaySummary) -> str | None:
        found = holiday_on(day.date, self._schedules.on(day.date).holidays) if day.day_type in _HOLIDAYS else None
        return found.name if found else None

    def _year_figures(self, days_worked: int, average: str, days_off: dict[DayType, int]) -> YearFigures:
        year = self._today.year
        first = max(dt.date(year, 1, 1), self._first)
        coding = CodingWork(self._store, self._user).by_service(first, dt.date(year, 12, 31), self._shows)
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
        items.append(ComingUp(start=day.date, end=day.date, day_type=DayType.WORK, holiday=None, days=0,
                              pto_days=0))  # a run breaker
        return
    last = items[-1] if items else None
    if _continues(last, day, holiday):
        items[-1] = last.model_copy(update={'end': day.date, 'days': last.days + 1,
                                            'pto_days': last.pto_days + float(day.pto_days)})
    else:
        items.append(ComingUp(start=day.date, end=day.date, day_type=day.day_type, holiday=holiday, days=1,
                              pto_days=float(day.pto_days)))


def _continues(last: ComingUp | None, day: DaySummary, holiday: str | None) -> bool:
    """Planned days off of one type in a row form one item; holidays stand alone."""
    return last is not None and holiday is None and last.holiday is None and last.day_type is day.day_type


def _months_back(date: dt.date, months: int) -> dt.date:
    """The first of the month `months` before the month of `date` (negative: after)."""
    index = date.year * 12 + date.month - 1 - months
    return dt.date(index // 12, index % 12 + 1, 1)
