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


@dataclass(frozen=True)
class PtoAccount:
    year: int
    carried_over: Decimal
    allowance: Decimal
    used: Decimal
    planned: Decimal  # PTO after the cut-off date, e.g. booked holidays

    @property
    def remaining(self) -> Decimal:
        return self.carried_over + self.allowance - self.used - self.planned


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


def allowance_for(allowances: Mapping[int, Decimal], year: int) -> Decimal:
    """Allowance of the latest configured year up to `year` ({2024: 18, 2025: 30} → 30 for 2027)."""
    configured = [configured_year for configured_year in allowances if configured_year <= year]
    if not configured:
        raise ValueError(f'No PTO allowance configured for {year}')
    return allowances[max(configured)]


def pto_accounts(records: Records, allowances: Mapping[int, Decimal], start: dt.date, until: dt.date) -> list[PtoAccount]:
    """PTO per year from start's year to until's year; the remaining days carry over into the next year.

    PTO on or before `until` is used, PTO after it (up to the end of its year) is planned.
    """
    accounts, carried_over = [], Decimal(0)
    for year in range(start.year, until.year + 1):
        days = summarize_period(records, max(start, dt.date(year, 1, 1)), dt.date(year, 12, 31))
        account = PtoAccount(
            year=year,
            carried_over=carried_over,
            allowance=allowance_for(allowances, year),
            used=sum((day.pto_days for day in days if day.date <= until), Decimal(0)),
            planned=sum((day.pto_days for day in days if day.date > until), Decimal(0)),
        )
        accounts.append(account)
        carried_over = account.remaining
    return accounts
