"""Reports for a week, a month (with the coding work by service) and a year (with the PTO account).

Worked time, target and overtime count up to today; future days do not count yet. Days off count for
the whole period, so planned PTO shows up.
"""

import calendar
import datetime as dt
import sqlite3
from collections import Counter, defaultdict

from pydantic import BaseModel, Field

from src.lib.balances import DayRecord, overtime_balance, pto_accounts, summarize_period
from src.lib.daytypes import DaySummary, DayType
from src.lib.durations import format_duration, parse_duration
from src.models.entries import TicketEntry
from src.modules.storage.catalog import ServiceRepository
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.pto_years import PtoYearRepository
from src.modules.storage.schedules import ScheduleRepository
from src.modules.storage.settings import load_settings
from src.modules.storage.tickets import TicketRepository

Records = dict[dt.date, DayRecord]


class PeriodTotals(BaseModel):
    start: dt.date
    end: dt.date
    until: dt.date | None = Field(description='Last day counted (today at the latest); null if nothing counted yet')
    worked: str
    target: str
    overtime: str
    balance_in: str = Field(description='Overtime balance before the period')
    balance_out: str = Field(description='Overtime balance at the end of the period (today at the latest)')


class WeekReport(BaseModel):
    week: str = Field(examples=['2026-W44'])
    totals: PeriodTotals
    days_off: dict[DayType, int] = Field(description='Weekdays by day type other than work, including planned ones')


class TicketWork(BaseModel):
    ticket_key: str | None = Field(description='Null for PR reviews still without ticket')
    duration: str
    descriptions: list[str]


class ServiceWork(BaseModel):
    service_id: int | None = Field(description='Null for tickets without service')
    service: str | None
    duration: str
    tickets: list[TicketWork]


class MonthReport(BaseModel):
    month: str = Field(examples=['2026-10'])
    totals: PeriodTotals
    days_off: dict[DayType, int]
    pto_days: float = Field(description='PTO used and planned in the month')
    coding: list[ServiceWork] = Field(description='Coding work by service and ticket; tickets without service last')
    coding_total: str


class MonthTotals(BaseModel):
    month: str
    worked: str
    target: str
    overtime: str


class PtoView(BaseModel):
    carried_over: float
    carried_over_fixed: bool = Field(description='Entered for the year instead of the remainder of the year before')
    allowance: float
    extra_days: float = Field(description='Days granted on top of the allowance')
    used: float
    planned: float
    remaining: float


class YearReport(BaseModel):
    year: int
    totals: PeriodTotals
    months: list[MonthTotals]
    days_worked: int = Field(description='Days with worked time, up to today')
    average_per_day_worked: str
    days_off: dict[DayType, int]
    pto: PtoView | None = Field(
        description='Null for years before the balance start, in the future or without PTO days entered',
    )


class Reports:
    """Builds a user's reports within the transaction of the given connection."""

    def __init__(self, conn: sqlite3.Connection, user_id: str, today: dt.date) -> None:
        self._conn = conn
        self._user = user_id
        self._today = today
        self._settings = load_settings(conn, user_id)
        self._pto_terms = PtoYearRepository(conn, user_id).terms()
        self._schedules = ScheduleRepository(conn, user_id).schedules()

    def week(self, week: str, monday: dt.date) -> WeekReport:
        sunday = monday + dt.timedelta(days=6)
        records = self._records(sunday)
        totals, days_off = self._totals(records, monday, sunday), self._days_off(records, monday, sunday)
        return WeekReport(week=week, totals=totals, days_off=days_off)

    def month(self, year: int, month: int) -> MonthReport:
        start, end = _month_bounds(year, month)
        records = self._records(end)
        coding = CodingWork(self._conn, self._user).by_service(start, end)
        return MonthReport(
            month=f'{year}-{month:02d}',
            totals=self._totals(records, start, end),
            days_off=self._days_off(records, start, end),
            pto_days=float(sum(day.pto_days for day in self._period_days(records, start, end))),
            coding=coding,
            coding_total=format_duration(sum(parse_duration(service.duration) for service in coding)),
        )

    def year(self, year: int) -> YearReport:
        start, end = dt.date(year, 1, 1), dt.date(year, 12, 31)
        records = self._records(end)
        counted = self._counted_days(records, start, end)
        worked_days = [day for day in counted if day.worked]
        return YearReport(
            year=year,
            totals=self._totals(records, start, end),
            months=[self._month_totals(records, year, month) for month in range(1, 13)],
            days_worked=len(worked_days),
            average_per_day_worked=format_duration(sum(day.worked for day in worked_days) // max(len(worked_days), 1)),
            days_off=self._days_off(records, start, end),
            pto=self._pto(records, year),
        )

    def _records(self, end: dt.date) -> Records:
        return DayRepository(self._conn, self._user).records(self._settings.balance_start, end)

    def _period_days(self, records: Records, start: dt.date, end: dt.date) -> list[DaySummary]:
        """Days of the period from the balance start on (days before it are ignored)."""
        first = max(start, self._settings.balance_start)
        return summarize_period(records, first, end, self._schedules) if first <= end else []

    def _counted_days(self, records: Records, start: dt.date, end: dt.date) -> list[DaySummary]:
        """Days of the period from the balance start up to today."""
        return self._period_days(records, start, min(end, self._today))

    def _days_off(self, records: Records, start: dt.date, end: dt.date) -> dict[DayType, int]:
        """Weekdays by day type other than work, including planned ones."""
        days = self._period_days(records, start, end)
        counts = Counter(day.day_type for day in days if day.work_day and day.day_type is not DayType.WORK)
        return dict(sorted(counts.items()))

    def _balance(self, records: Records, until: dt.date) -> int:
        return overtime_balance(records, self._settings.balance_start, until, self._settings.opening_balance, self._schedules)

    def _totals(self, records: Records, start: dt.date, end: dt.date) -> PeriodTotals:
        days = self._counted_days(records, start, end)
        worked, target = sum(day.worked for day in days), sum(day.target for day in days)
        balance_in = self._balance(records, start - dt.timedelta(days=1))
        return PeriodTotals(
            start=start,
            end=end,
            until=days[-1].date if days else None,
            worked=format_duration(worked),
            target=format_duration(target),
            overtime=format_duration(worked - target),
            balance_in=format_duration(balance_in),
            balance_out=format_duration(balance_in + worked - target),
        )

    def _month_totals(self, records: Records, year: int, month: int) -> MonthTotals:
        totals = self._totals(records, *_month_bounds(year, month))
        return MonthTotals(month=f'{year}-{month:02d}', worked=totals.worked, target=totals.target, overtime=totals.overtime)

    def _pto(self, records: Records, year: int) -> PtoView | None:
        if not self._settings.balance_start.year <= year <= self._today.year:
            return None
        until = min(dt.date(year, 12, 31), self._today)
        accounts = pto_accounts(records, self._pto_terms, self._settings.balance_start, until, self._schedules)
        account = next((account for account in accounts if account.year == year), None)
        if account is None:
            return None
        return PtoView(
            carried_over=float(account.carried_over), carried_over_fixed=self._pto_terms[year].carried_over is not None,
            allowance=float(account.allowance), extra_days=float(account.extra_days), used=float(account.used),
            planned=float(account.planned), remaining=float(account.remaining),
        )


class CodingWork:
    """A user's coding entries of a period, grouped by the service of their ticket and by ticket."""

    def __init__(self, conn: sqlite3.Connection, user_id: str) -> None:
        self._entries = EntryRepository(conn, user_id)
        self._ticket_services = {ticket.key: ticket.service_id for ticket in TicketRepository(conn, user_id).all()}
        self._services = {service.id: service.short_name for service in ServiceRepository(conn, user_id).all()}

    def by_service(self, start: dt.date, end: dt.date) -> list[ServiceWork]:
        grouped = defaultdict(lambda: defaultdict(list))
        for entry in self._entries.between(start, end):
            if isinstance(entry, TicketEntry) and entry.coding:
                grouped[self._ticket_services.get(entry.ticket_key)][entry.ticket_key].append(entry)
        services = sorted(grouped, key=lambda service_id: (service_id is None, (self._services.get(service_id) or '').lower()))
        return [self._service_work(service_id, grouped[service_id]) for service_id in services]

    def _service_work(self, service_id: int | None, tickets: dict[str | None, list[TicketEntry]]) -> ServiceWork:
        work = [_ticket_work(key, tickets[key]) for key in sorted(tickets, key=_ticket_order)]
        return ServiceWork(
            service_id=service_id,
            service=self._services.get(service_id),
            duration=format_duration(sum(parse_duration(ticket.duration) for ticket in work)),
            tickets=work,
        )


def _ticket_work(key: str | None, entries: list[TicketEntry]) -> TicketWork:
    descriptions: dict[str, str] = {}  # first spelling per description, ignoring case ('PR Review' = 'PR review')
    for entry in entries:
        if entry.description:
            descriptions.setdefault(entry.description.casefold(), entry.description)
    return TicketWork(ticket_key=key, duration=format_duration(sum(entry.duration for entry in entries)),
                      descriptions=list(descriptions.values()))


def _ticket_order(key: str | None) -> tuple[bool, str, int]:
    """By prefix and number (TNG-999 before TNG-5214); entries without ticket last."""
    if key is None:
        return True, '', 0
    prefix, number = key.rsplit('-', 1)
    return False, prefix, int(number)


def _month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])
