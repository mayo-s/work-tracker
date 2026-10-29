"""Report endpoints: /api/reports/weeks/{week}, /api/reports/months/{month}, /api/reports/years/{year}; `member` shows
a member of the team admin's team (team view, logged for the member)."""

import datetime as dt
import re
import sqlite3
from collections.abc import Callable

import falcon
from spectree import Response

from src.modules.reports.schemas import MonthReport, Reports, WeekReport, YearReport
from src.modules.storage.database import Database
from src.modules.teams.view import MemberQuery, viewing
from src.utils.spec import spec

TAGS = ['Reports']
_WEEK = re.compile(r'(\d{4})-W(\d{2})')

Today = Callable[[], dt.date]


class _Report:
    def __init__(
        self, database: Database, today: Today = dt.date.today, clock: Callable[[], dt.datetime] = dt.datetime.now,
    ) -> None:
        self._database = database
        self._today = today
        self._clock = clock

    def _reports(self, req: falcon.Request, conn: sqlite3.Connection, query: MemberQuery, report: str, period: str) -> Reports:
        """The reports of the user, or in the team view of the member (logged for them)."""
        view = viewing(req, conn, query.member)
        view.log(conn, report, period, self._clock())
        return Reports(conn, view.user_id, self._today(), view.visible_from)


class WeekReportResource(_Report):
    @spec.validate(query=MemberQuery, resp=Response('HTTP_403', 'HTTP_404', HTTP_200=WeekReport), tags=TAGS,
                   path_parameter_descriptions={'week': 'ISO week, e.g. 2026-W44'})
    def on_get(self, req: falcon.Request, resp: falcon.Response, week: str, query: MemberQuery) -> None:
        """Totals of a week (Monday to Sunday) and the overtime balance before and after it."""
        monday = _monday_of(week)
        with self._database.transaction() as conn:
            resp.media = self._reports(req, conn, query, 'week', week).week(week, monday)


class MonthReportResource(_Report):
    @spec.validate(query=MemberQuery, resp=Response('HTTP_403', HTTP_200=MonthReport), tags=TAGS,
                   path_parameter_descriptions={'month': 'Month, e.g. 2026-10'})
    def on_get(self, req: falcon.Request, resp: falcon.Response, month: dt.datetime, query: MemberQuery) -> None:
        """Totals of a month and the monthly work report: coding work by service and ticket."""
        with self._database.transaction() as conn:
            reports = self._reports(req, conn, query, 'month', f'{month.year}-{month.month:02d}')
            resp.media = reports.month(month.year, month.month)


class YearReportResource(_Report):
    @spec.validate(query=MemberQuery, resp=Response('HTTP_403', HTTP_200=YearReport), tags=TAGS,
                   path_parameter_descriptions={'year': 'Year, e.g. 2026'})
    def on_get(self, req: falcon.Request, resp: falcon.Response, year: int, query: MemberQuery) -> None:
        """Totals of a year, per month, and the PTO account (replaces the spreadsheet dashboard)."""
        with self._database.transaction() as conn:
            resp.media = self._reports(req, conn, query, 'year', str(year)).year(year)


def _monday_of(week: str) -> dt.date:
    """Monday of an ISO week like 2026-W44; 404 for anything else."""
    match = _WEEK.fullmatch(week)
    try:
        return dt.date.fromisocalendar(int(match[1]), int(match[2]), 1)
    except (TypeError, ValueError):
        raise falcon.HTTPNotFound(description=f'Unknown week {week}, expected e.g. 2026-W44') from None
