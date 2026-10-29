"""Overtime balance and PTO accounts over a period of days."""

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple

from src.lib.dates import each_day
from src.lib.daytypes import DaySummary, DayType, summarize_day


class DayRecord(NamedTuple):
    """What was recorded for a day; days without a record count as nothing worked, automatic day type."""

    worked: int = 0
    day_type: DayType | None = None


Records = Mapping[dt.date, DayRecord]


class PtoTerms(NamedTuple):
    """PTO days of a year: the allowance, days granted on top and an optional fixed carry-over."""

    allowance: Decimal
    extra_days: Decimal = Decimal(0)
    carried_over: Decimal | None = None  # None: the remainder of the year before


@dataclass(frozen=True)
class PtoAccount:
    year: int
    carried_over: Decimal
    allowance: Decimal
    extra_days: Decimal
    used: Decimal
    planned: Decimal  # PTO after the cut-off date, e.g. booked holidays

    @property
    def remaining(self) -> Decimal:
        return self.carried_over + self.allowance + self.extra_days - self.used - self.planned


def summarize_period(records: Records, start: dt.date, end: dt.date) -> list[DaySummary]:
    """A summary for every calendar day from start to end (inclusive)."""
    return [summarize_day(day, *records.get(day, DayRecord())) for day in each_day(start, end)]


def overtime_balance(records: Records, start: dt.date, until: dt.date, opening: int = 0) -> int:
    """Opening balance plus the overtime of every day from start to until (inclusive).

    Pass today (or an earlier date) as `until`: future days must not count.
    """
    if until < start:
        return opening
    return opening + sum(day.overtime for day in summarize_period(records, start, until))


def pto_accounts(records: Records, terms: Mapping[int, PtoTerms], start: dt.date, until: dt.date) -> list[PtoAccount]:
    """PTO per year from start's year to until's year, for the years with terms.

    The carry-over is the fixed one of the terms, otherwise the remainder of the year before (nothing in start's
    year). A year without terms has no account, so the year after it needs a fixed carry-over to have one.
    PTO on or before `until` is used, PTO after it (up to the end of its year) is planned.
    """
    accounts: list[PtoAccount] = []
    remainder: Decimal | None = Decimal(0)
    for year in range(start.year, until.year + 1):
        account = _pto_account(records, year, terms.get(year), remainder, max(start, dt.date(year, 1, 1)), until)
        if account:
            accounts.append(account)
        remainder = account.remaining if account else None
    return accounts


def _pto_account(
    records: Records, year: int, terms: PtoTerms | None, remainder: Decimal | None, start: dt.date, until: dt.date,
) -> PtoAccount | None:
    carried_over = _carried_over(terms, remainder)
    if terms is None or carried_over is None:
        return None
    used, planned = _used_and_planned(summarize_period(records, start, dt.date(year, 12, 31)), until)
    return PtoAccount(year, carried_over, terms.allowance, terms.extra_days, used, planned)


def _carried_over(terms: PtoTerms | None, remainder: Decimal | None) -> Decimal | None:
    """The fixed carry-over of the terms, otherwise the remainder of the year before (None if unknown)."""
    return terms.carried_over if terms and terms.carried_over is not None else remainder


def _used_and_planned(days: list[DaySummary], until: dt.date) -> tuple[Decimal, Decimal]:
    """PTO days on or before `until` (used) and after it (planned)."""
    used = sum((day.pto_days for day in days if day.date <= until), Decimal(0))
    return used, sum((day.pto_days for day in days), Decimal(0)) - used
