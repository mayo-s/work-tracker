"""Report endpoints: /api/reports/weeks/{week}, /api/reports/months/{month}, /api/reports/years/{year}."""

import datetime as dt
import re
from collections.abc import Callable

import falcon
from spectree import Response

from src.modules.reports.schemas import MonthReport, Reports, WeekReport, YearReport
from src.modules.storage.database import Database
from src.modules.auth.sessions import current_user
from src.utils.spec import spec

TAGS = ['Reports']
_WEEK = re.compile(r'(\d{4})-W(\d{2})')

Today = Callable[[], dt.date]


class _Report:
    def __init__(self, database: Database, today: Today = dt.date.today) -> None:
        self._database = database
        self._today = today


class WeekReportResource(_Report):
    @spec.validate(resp=Response('HTTP_404', HTTP_200=WeekReport), tags=TAGS,
                   path_parameter_descriptions={'week': 'ISO week, e.g. 2026-W44'})
    def on_get(self, req: falcon.Request, resp: falcon.Response, week: str) -> None:
        """Totals of a week (Monday to Sunday) and the overtime balance before and after it."""
        monday = _monday_of(week)
        with self._database.transaction() as conn:
            resp.media = Reports(conn, current_user(req), self._today()).week(week, monday)


class MonthReportResource(_Report):
    @spec.validate(resp=Response(HTTP_200=MonthReport), tags=TAGS,
                   path_parameter_descriptions={'month': 'Month, e.g. 2026-10'})
    def on_get(self, req: falcon.Request, resp: falcon.Response, month: dt.datetime) -> None:
        """Totals of a month and the monthly work report: coding work by service and ticket."""
        with self._database.transaction() as conn:
            resp.media = Reports(conn, current_user(req), self._today()).month(month.year, month.month)


class YearReportResource(_Report):
    @spec.validate(resp=Response(HTTP_200=YearReport), tags=TAGS, path_parameter_descriptions={'year': 'Year, e.g. 2026'})
    def on_get(self, req: falcon.Request, resp: falcon.Response, year: int) -> None:
        """Totals of a year, per month, and the PTO account (replaces the spreadsheet dashboard)."""
        with self._database.transaction() as conn:
            resp.media = Reports(conn, current_user(req), self._today()).year(year)


def _monday_of(week: str) -> dt.date:
    """Monday of an ISO week like 2026-W44; 404 for anything else."""
    match = _WEEK.fullmatch(week)
    try:
        return dt.date.fromisocalendar(int(match[1]), int(match[2]), 1)
    except (TypeError, ValueError):
        raise falcon.HTTPNotFound(description=f'Unknown week {week}, expected e.g. 2026-W44') from None
