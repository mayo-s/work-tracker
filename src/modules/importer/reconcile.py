"""Comparing an imported year with the spreadsheet: the sheet counts `Sum` − 8:00 as overtime on every day."""

import datetime as dt
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from src.lib.balances import DayRecord, PtoAccount, Records, overtime_balance, pto_accounts
from src.lib.daytypes import summarize_day
from src.lib.durations import format_duration
from src.lib.schedules import Schedules
from src.modules.importer.days import SHEET_DAY
from src.modules.importer.sheet import SheetRow
from src.modules.storage.days import DayRepository
from src.modules.storage.pto_years import PtoYearRepository
from src.modules.storage.schedules import ScheduleRepository
from src.modules.storage.settings import load_settings


@dataclass(frozen=True)
class DayDifference:
    date: dt.date
    sheet: int  # the sheet's overtime of the day
    app: int  # the app's overtime of the day
    comment: str


@dataclass(frozen=True)
class Reconciliation:
    year: int
    until: dt.date  # last day compared (today, or the end of the year)
    sheet_overtime: int
    app_overtime: int
    differences: tuple[DayDifference, ...]
    balance: int  # overtime balance on `until`, including earlier years
    pto: PtoAccount | None  # None for years before the balance start or without PTO days entered

    def lines(self) -> list[str]:
        result = [
            f'Reconciliation {self.year} (up to {self.until:%d.%m.%Y})',
            f'  Overtime:    sheet {format_duration(self.sheet_overtime)}, app {format_duration(self.app_overtime)}'
            f' — {len(self.differences) or "no"} days differ',
            *(f'    {diff.date:%d.%m.%Y}: sheet {format_duration(diff.sheet)}, app {format_duration(diff.app)}  {diff.comment}'
              for diff in self.differences),
            f'  Balance:     {format_duration(self.balance)} on {self.until:%d.%m.%Y}',
        ]
        if self.pto:
            result.append(
                f'  PTO:         {self.pto.carried_over} carried over + {self.pto.allowance} allowance'
                f' + {self.pto.extra_days} extra'
                f' − {self.pto.used} used − {self.pto.planned} planned = {self.pto.remaining} remaining'
            )
        return result


def reconcile(conn: sqlite3.Connection, user_id: str, rows: Sequence[SheetRow], today: dt.date) -> Reconciliation:
    """Compare the user's imported days of the rows' year with the sheet, up to today (future days do not count yet)."""
    settings = load_settings(conn, user_id)
    year = rows[0].date.year
    until = min(today, dt.date(year, 12, 31))
    records = DayRepository(conn, user_id).records(settings.balance_start, dt.date(year, 12, 31))
    schedules = ScheduleRepository(conn, user_id).schedules()
    compared = [row for row in rows if settings.balance_start <= row.date <= until]
    accounts = pto_accounts(records, PtoYearRepository(conn, user_id).terms(), settings.balance_start, until, schedules)
    return Reconciliation(
        year=year,
        until=until,
        sheet_overtime=sum(row.total - SHEET_DAY for row in compared),
        app_overtime=sum(_app_overtime(row.date, records, schedules) for row in compared),
        differences=_differences(compared, records, schedules),
        balance=overtime_balance(records, settings.balance_start, until, settings.opening_balance, schedules),
        pto=_account_of(accounts, year),
    )


def _account_of(accounts: list[PtoAccount], year: int) -> PtoAccount | None:
    return next((account for account in accounts if account.year == year), None)


def _differences(rows: Sequence[SheetRow], records: Records, schedules: Schedules) -> tuple[DayDifference, ...]:
    return tuple(diff for row in rows if (diff := _difference(row, records, schedules)))


def _app_overtime(date: dt.date, records: Records, schedules: Schedules) -> int:
    return summarize_day(date, *records.get(date, DayRecord()), schedules.on(date)).overtime


def _difference(row: SheetRow, records: Records, schedules: Schedules) -> DayDifference | None:
    sheet, app = row.total - SHEET_DAY, _app_overtime(row.date, records, schedules)
    return None if sheet == app else DayDifference(row.date, sheet, app, ' | '.join(row.comment))
