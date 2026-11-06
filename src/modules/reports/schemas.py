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
    ticket_key: str | None = Field(description='Null for entries still without the ticket their activity type requires')
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
    services: list[ServiceWork] = Field(
        description='Its entries on a ticket by service and ticket (with those still without the ticket their activity type '
                    'requires); tickets without service last')
    descriptions: list[str] = Field(description='The descriptions of its other entries')


Entries = Annotated[str, Field(description='Hours in entries on the days counted as worked (up to today)')]


class MonthReport(BaseModel):
    month: str = Field(examples=['2026-10'])
    totals: PeriodTotals
    entries: Entries
    days_off: dict[DayType, int]
    pto_days: float = Field(description='PTO used and planned in the month')
    work: list[ActivityWork] = Field(description='The work by activity type, most hours first')
    work_total: str = Field(description='Hours in all entries of the month')
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
    work: list[ActivityTotal] = Field(description='The work by activity type, most hours first')
    work_total: str = Field(description='Hours in all entries of the year')
    services: list[ServiceTotal] = Field(description='The work on tickets by service, most hours first; without service last')
    services_total: str
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
        by_type = work.activity_types()
        return MonthReport(
            month=f'{year}-{month:02d}',
            totals=self._totals(ledger, start, end),
            entries=work.total(min(end, self._today)),
            days_off=self._days_off(ledger, start, end),
            pto_days=float(sum(day.pto_days for day in self._period_days(ledger, start, end))),
            work=by_type, work_total=_sum(by_type),
            visible_from=self._visible_from,
        )

    def year(self, year: int) -> YearReport:
        start, end = dt.date(year, 1, 1), dt.date(year, 12, 31)
        ledger = self._ledger_until(end)
        counted = self._counted_days(ledger, start, end)
        worked_days = [day for day in counted if day.worked]
        work = self._work(start, end)
        by_type, services = work.activity_types(), work.services()
        return YearReport(
            year=year,
            totals=self._totals(ledger, start, end),
            entries=work.total(min(end, self._today)),
            months=[self._month_totals(ledger, year, month) for month in range(1, 13)],
            days_worked=len(worked_days),
            average_per_day_worked=format_duration(sum(day.worked for day in worked_days) // max(len(worked_days), 1)),
            days_off=self._days_off(ledger, start, end),
            pto=self._pto(year),
            work=[ActivityTotal(**item.model_dump(exclude={'services', 'descriptions'})) for item in by_type],
            work_total=_sum(by_type),
            services=_service_totals(services), services_total=_sum(services),
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
    """A user's entries from `start` to `end` (with `shows`, team view: only on the days shown): the work by activity
    type, each with its entries on a ticket by service and ticket, and the work on tickets by service."""

    def __init__(self, store: Store, user_id: str, start: dt.date, end: dt.date, shows: Shows = None) -> None:
        self._entries = [entry for entry in store.entries(user_id).between(start, end) if shows is None or shows(entry.date)]
        self._services = TicketServices(store, user_id)
        self._activity_types = {kind.id: kind for kind in store.activity_types(user_id).all()}

    def activity_types(self) -> list[ActivityWork]:
        """The work by activity type, most hours first (then by name)."""
        grouped = defaultdict(list)
        for entry in self._entries:
            grouped[entry.activity_type_id].append(entry)
        work = [self._activity_work(type_id, entries) for type_id, entries in grouped.items()]
        return sorted(work, key=lambda item: (-parse_duration(item.duration), item.activity_type.lower()))

    def services(self) -> list[ServiceWork]:
        """The work on tickets by service, most hours first; tickets without service last."""
        by_service = self._by_service([entry for entry in self._entries if self._on_ticket(entry)])
        return sorted(by_service, key=lambda work: (work.service_id is None, -parse_duration(work.duration)))

    def total(self, until: dt.date) -> str:
        """The hours in all entries up to `until`."""
        return format_duration(sum(entry.duration for entry in self._entries if entry.date <= until))

    def _activity_work(self, type_id: str | None, entries: list[Entry]) -> ActivityWork:
        return ActivityWork(
            activity_type_id=type_id, activity_type=self._name(type_id),
            duration=format_duration(sum(entry.duration for entry in entries)),
            services=self._by_service([entry for entry in entries if self._on_ticket(entry)]),
            descriptions=_distinct(entry.description for entry in entries if not self._on_ticket(entry)),
        )

    def _name(self, type_id: str | None) -> str:
        kind = self._activity_types.get(type_id)
        return kind.name if kind else 'No activity type'  # a former entry still waiting for the review

    def _on_ticket(self, entry: Entry) -> bool:
        """On a ticket, or still without the ticket its activity type requires (e.g. an imported PR review)."""
        kind = self._activity_types.get(entry.activity_type_id)
        return entry.ticket_key is not None or bool(kind and kind.ticket_required)

    def _by_service(self, entries: list[Entry]) -> list[ServiceWork]:
        """By service, ordered by name, and by ticket; tickets without service last."""
        grouped = defaultdict(lambda: defaultdict(list))
        for entry in entries:
            grouped[self._services.of_ticket(entry.ticket_key)][entry.ticket_key].append(entry)
        services = sorted(grouped, key=lambda service: (service is None, (self._services.name(service) or '').lower()))
        return [self._service_work(service_id, grouped[service_id]) for service_id in services]

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
