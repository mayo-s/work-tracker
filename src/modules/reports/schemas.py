"""Reports for a week, a month (with the work by service, ticket and activity type) and a year (with the PTO account
and the work by service and activity type).

Worked time, target and overtime count up to today; future days do not count yet. Days off count for
the whole period, so planned PTO shows up. In the team view, the period figures count only the member's days in the
team (Stays); the balance and the PTO account are running figures and cover the whole time.
"""

import calendar
import datetime as dt
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from typing import Annotated

from pydantic import BaseModel, Field

from src.lib.balances import DayLedger, DayRecord, pto_accounts
from src.lib.daytypes import DaySummary, DayType
from src.lib.durations import format_duration, parse_duration
from src.lib.stays import Stays
from src.models.entries import Entry
from src.modules.storage.store import Store
from src.modules.tickets.schemas import TicketServices

Records = dict[dt.date, DayRecord]
VisibleFrom = Annotated[dt.date | None, Field(description='Team view: the first day shown (the member joined the team)')]
Shows = Callable[[dt.date], bool] | None  # team view: whether a day is shown (one of the member's days in the team)


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
    visible_from: VisibleFrom = None


class TicketWork(BaseModel):
    ticket_key: str | None = Field(description='Null for PR reviews still without ticket')
    duration: str
    descriptions: list[str]


class ServiceTotal(BaseModel):
    service_id: str | None = Field(description='Null for tickets without service')
    service: str | None
    duration: str


class ServiceWork(ServiceTotal):
    tickets: list[TicketWork]


class ActivityTotal(BaseModel):
    activity_type_id: str | None = Field(description='None: entries still without activity type (see the review)')
    activity_type: str
    duration: str


class ActivityWork(ActivityTotal):
    notes: list[str]


Entries = Annotated[str, Field(description='Hours in entries on the days counted as worked (up to today)')]


class MonthReport(BaseModel):
    month: str = Field(examples=['2026-10'])
    totals: PeriodTotals
    entries: Entries
    days_off: dict[DayType, int]
    pto_days: float = Field(description='PTO used and planned in the month')
    coding: list[ServiceWork] = Field(description='Coding work by service and ticket; tickets without service last')
    coding_total: str
    other_work: list[ServiceWork] = Field(description='Ticket work not marked as coding, by service and ticket')
    other_work_total: str
    activities: list[ActivityWork] = Field(description='Activities by type, with their notes')
    activities_total: str
    visible_from: VisibleFrom = None


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
    entries: Entries
    months: list[MonthTotals]
    days_worked: int = Field(description='Days with worked time, up to today')
    average_per_day_worked: str
    days_off: dict[DayType, int]
    pto: PtoView | None = Field(
        description='Null for years before the balance start, in the future or without PTO days entered',
    )
    coding: list[ServiceTotal] = Field(description='Coding work by service; tickets without service last')
    coding_total: str
    other_work: list[ServiceTotal] = Field(description='Ticket work not marked as coding, by service')
    other_work_total: str
    activities: list[ActivityTotal] = Field(description='Activities by type')
    activities_total: str
    visible_from: VisibleFrom = None


class Reports:
    """Builds a user's reports within the transaction of the given store; with `stays` (team view), period figures
    count only the days shown."""

    def __init__(self, store: Store, user_id: str, today: dt.date, stays: Stays | None = None) -> None:
        self._store = store
        self._user = user_id
        self._today = today
        self._visible_from = stays.first if stays else None
        self._shows: Shows = stays.shows if stays else None
        self._settings = store.load_settings(user_id)
        self._first = max(self._settings.balance_start, self._visible_from or dt.date.min)
        self._pto_terms = store.pto_years(user_id).terms()
        self._schedules = store.schedules(user_id).schedules()
        self._records: Records = {}
        self._loaded: DayLedger | None = None

    def week(self, week: str, monday: dt.date) -> WeekReport:
        sunday = monday + dt.timedelta(days=6)
        ledger = self._ledger_until(sunday)
        totals, days_off = self._totals(ledger, monday, sunday), self._days_off(ledger, monday, sunday)
        return WeekReport(week=week, totals=totals, days_off=days_off, visible_from=self._visible_from)

    def month(self, year: int, month: int) -> MonthReport:
        start, end = _month_bounds(year, month)
        ledger = self._ledger_until(end)
        work = self._work(start, end)
        coding, other, activities = work.tickets(coding=True), work.tickets(coding=False), work.activities()
        return MonthReport(
            month=f'{year}-{month:02d}',
            totals=self._totals(ledger, start, end),
            entries=work.total(min(end, self._today)),
            days_off=self._days_off(ledger, start, end),
            pto_days=float(sum(day.pto_days for day in self._period_days(ledger, start, end))),
            coding=coding, coding_total=_sum(coding),
            other_work=other, other_work_total=_sum(other),
            activities=activities, activities_total=_sum(activities),
            visible_from=self._visible_from,
        )

    def year(self, year: int) -> YearReport:
        start, end = dt.date(year, 1, 1), dt.date(year, 12, 31)
        ledger = self._ledger_until(end)
        counted = self._counted_days(ledger, start, end)
        worked_days = [day for day in counted if day.worked]
        work = self._work(start, end)
        coding, other, activities = work.tickets(coding=True), work.tickets(coding=False), work.activities()
        return YearReport(
            year=year,
            totals=self._totals(ledger, start, end),
            entries=work.total(min(end, self._today)),
            months=[self._month_totals(ledger, year, month) for month in range(1, 13)],
            days_worked=len(worked_days),
            average_per_day_worked=format_duration(sum(day.worked for day in worked_days) // max(len(worked_days), 1)),
            days_off=self._days_off(ledger, start, end),
            pto=self._pto(year),
            coding=_service_totals(coding), coding_total=_sum(coding),
            other_work=_service_totals(other), other_work_total=_sum(other),
            activities=[ActivityTotal(**item.model_dump(exclude={'notes'})) for item in activities],
            activities_total=_sum(activities),
            visible_from=self._visible_from,
        )

    def _work(self, start: dt.date, end: dt.date) -> 'PeriodWork':
        """The entries of the period from the balance start on (in the team view only on the days shown)."""
        return PeriodWork(self._store, self._user, max(start, self._first), end, self._shows)

    def _ledger_until(self, end: dt.date) -> DayLedger:
        """The days from the balance start to `end` at least, loaded and summarized once per report object (the
        dashboard asks for several periods)."""
        if self._loaded is None or self._loaded.end < end:
            start = self._settings.balance_start
            self._records = self._store.days(self._user).records(start, end) if start <= end else {}
            self._loaded = DayLedger(self._records, start, end, self._today, self._settings.opening_balance,
                                     self._schedules)
        return self._loaded

    def _period_days(self, ledger: DayLedger, start: dt.date, end: dt.date) -> list[DaySummary]:
        """Days of the period from the balance start on (days before it are ignored; in the team view also those not
        shown)."""
        return self._only_shown(ledger.days(max(start, self._first), end))

    def _only_shown(self, days: list[DaySummary]) -> list[DaySummary]:
        """In the team view only the days shown, all others otherwise."""
        return [day for day in days if self._shows(day.date)] if self._shows else days

    def _counted_days(self, ledger: DayLedger, start: dt.date, end: dt.date) -> list[DaySummary]:
        """Days of the period from the balance start up to today."""
        return self._period_days(ledger, start, min(end, self._today))

    def _days_off(self, ledger: DayLedger, start: dt.date, end: dt.date) -> dict[DayType, int]:
        """Weekdays by day type other than work, including planned ones."""
        days = self._period_days(ledger, start, end)
        counts = Counter(day.day_type for day in days if day.work_day and day.day_type is not DayType.WORK)
        return dict(sorted(counts.items()))

    def _totals(self, ledger: DayLedger, start: dt.date, end: dt.date) -> PeriodTotals:
        days = self._counted_days(ledger, start, end)
        worked, target = sum(day.worked for day in days), sum(day.target for day in days)
        balance_in = ledger.balance(start - dt.timedelta(days=1))
        return PeriodTotals(
            start=start,
            end=end,
            until=days[-1].date if days else None,
            worked=format_duration(worked),
            target=format_duration(target),
            overtime=format_duration(worked - target),
            balance_in=format_duration(balance_in),
            balance_out=format_duration(ledger.balance(days[-1].date) if days else balance_in),
        )

    def _month_totals(self, ledger: DayLedger, year: int, month: int) -> MonthTotals:
        totals = self._totals(ledger, *_month_bounds(year, month))
        return MonthTotals(month=f'{year}-{month:02d}', worked=totals.worked, target=totals.target, overtime=totals.overtime)

    def _pto(self, year: int) -> PtoView | None:
        if not self._settings.balance_start.year <= year <= self._today.year:
            return None
        until = min(dt.date(year, 12, 31), self._today)
        accounts = pto_accounts(self._records, self._pto_terms, self._settings.balance_start, until, self._schedules)
        account = next((account for account in accounts if account.year == year), None)
        if account is None:
            return None
        return PtoView(
            carried_over=float(account.carried_over), carried_over_fixed=self._pto_terms[year].carried_over is not None,
            allowance=float(account.allowance), extra_days=float(account.extra_days), used=float(account.used),
            planned=float(account.planned), remaining=float(account.remaining),
        )


class PeriodWork:
    """A user's entries from `start` to `end` (with `shows`, team view: only on the days shown): the ticket work by the
    service of the ticket and by ticket, coding or not, and the activities by type.

    Until the work report goes by activity type (TASKS.md 13.9), coding work is the work of activity types that require
    a ticket (Coding), other ticket work that of other entries with a ticket, and activities the entries without one."""

    def __init__(self, store: Store, user_id: str, start: dt.date, end: dt.date, shows: Shows = None) -> None:
        self._entries = [entry for entry in store.entries(user_id).between(start, end) if shows is None or shows(entry.date)]
        self._services = TicketServices(store, user_id)
        self._activity_types = {kind.id: kind for kind in store.activity_types(user_id).all()}

    def tickets(self, coding: bool) -> list[ServiceWork]:
        """The coding work, or the other ticket work; tickets without service last."""
        grouped = defaultdict(lambda: defaultdict(list))
        for entry in self._entries:
            if self._ticket_work(entry, coding):
                grouped[self._services.of_ticket(entry.ticket_key)][entry.ticket_key].append(entry)
        services = sorted(grouped, key=lambda service: (service is None, (self._services.name(service) or '').lower()))
        return [self._service_work(service_id, grouped[service_id]) for service_id in services]

    def activities(self) -> list[ActivityWork]:
        """The entries without a ticket by activity type, ordered by name, with their descriptions."""
        grouped = defaultdict(list)
        for entry in self._entries:
            if not self._coding(entry) and entry.ticket_key is None:
                grouped[entry.activity_type_id].append(entry)
        names = {type_id: kind.name for type_id, kind in self._activity_types.items()}
        work = [_activity_work(type_id, names.get(type_id, 'No activity type'), entries)
                for type_id, entries in grouped.items()]
        return sorted(work, key=lambda activity: activity.activity_type.lower())

    def total(self, until: dt.date) -> str:
        """The hours in all entries up to `until`."""
        return format_duration(sum(entry.duration for entry in self._entries if entry.date <= until))

    def _ticket_work(self, entry: Entry, coding: bool) -> bool:
        """Coding work (with or without its ticket), or other work on a ticket."""
        return self._coding(entry) if coding else not self._coding(entry) and entry.ticket_key is not None

    def _coding(self, entry: Entry) -> bool:
        kind = self._activity_types.get(entry.activity_type_id)
        return bool(kind and kind.ticket_required)

    def _service_work(self, service_id: str | None, tickets: dict[str | None, list[Entry]]) -> ServiceWork:
        work = [_ticket_work(key, tickets[key]) for key in sorted(tickets, key=_ticket_order)]
        return ServiceWork(
            service_id=service_id,
            service=self._services.name(service_id),
            duration=format_duration(sum(parse_duration(ticket.duration) for ticket in work)),
            tickets=work,
        )


def _ticket_work(key: str | None, entries: list[Entry]) -> TicketWork:
    return TicketWork(ticket_key=key, duration=format_duration(sum(entry.duration for entry in entries)),
                      descriptions=_distinct(entry.description for entry in entries))


def _activity_work(type_id: str | None, name: str, entries: list[Entry]) -> ActivityWork:
    return ActivityWork(activity_type_id=type_id, activity_type=name,
                        duration=format_duration(sum(entry.duration for entry in entries)),
                        notes=_distinct(entry.description for entry in entries))


def _distinct(texts: Iterable[str]) -> list[str]:
    """The texts without empty ones and repeats, in the first spelling ignoring case ('PR Review' = 'PR review')."""
    first: dict[str, str] = {}
    for text in texts:
        if text:
            first.setdefault(text.casefold(), text)
    return list(first.values())


def _service_totals(work: list[ServiceWork]) -> list[ServiceTotal]:
    """The services without their tickets (the year report)."""
    return [ServiceTotal(**service.model_dump(exclude={'tickets'})) for service in work]


def _sum(work: list[ServiceWork] | list[ActivityWork]) -> str:
    return format_duration(sum(parse_duration(item.duration) for item in work))


def _ticket_order(key: str | None) -> tuple[bool, str, int]:
    """By prefix and number (TNG-999 before TNG-5214); entries without ticket last."""
    if key is None:
        return True, '', 0
    prefix, number = key.rsplit('-', 1)
    return False, prefix, int(number)


def _month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])
