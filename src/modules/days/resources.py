"""Days endpoints: /api/days, /api/days/{date} and /api/days/range."""

import datetime as dt
import sqlite3
from collections import defaultdict

import falcon
from spectree import Response

from src.lib.dates import each_day
from src.models.review import ReviewFlag
from src.modules.days.ranges import DayRangeInput, DayRangeResult, book_range
from src.modules.days.schemas import DayInput, DayView, day_view
from src.modules.storage.database import Database
from src.modules.storage.days import DayRepository
from src.modules.storage.schedules import ScheduleRepository
from src.utils.api import PeriodQuery
from src.utils.spec import spec

TAGS = ['Days']
DATE_PARAMETER = {'date': 'Date in ISO format, e.g. 2026-10-28'}


class DayCollection:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(query=PeriodQuery, resp=Response(HTTP_200=list[DayView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response, query: PeriodQuery) -> None:
        """Every calendar day of a week or date range, recorded or not."""
        start, end = query.period()
        with self._database.transaction() as conn:
            days = DayRepository(conn)
            recorded = {day.date: day for day in days.between(start, end)}
            flags = _flags_by_date(days.day_flags(), start, end)
            schedules = ScheduleRepository(conn).schedules()
        resp.media = [day_view(date, recorded.get(date), flags[date], schedules.on(date)) for date in each_day(start, end)]


class DayItem:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response(HTTP_200=DayView), tags=TAGS, path_parameter_descriptions=DATE_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, date: dt.datetime) -> None:
        """One calendar day, recorded or not."""
        with self._database.transaction() as conn:
            resp.media = _view(conn, date.date())

    @spec.validate(json=DayInput, resp=Response(HTTP_200=DayView), tags=TAGS, path_parameter_descriptions=DATE_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, date: dt.datetime, json: DayInput) -> None:
        """Record a day (insert or replace)."""
        with self._database.transaction() as conn:
            DayRepository(conn).save(json.to_day(date.date()))
            resp.media = _view(conn, date.date())

    @spec.validate(resp=Response('HTTP_204', 'HTTP_404'), tags=TAGS, path_parameter_descriptions=DATE_PARAMETER)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, date: dt.datetime) -> None:
        """Delete a recorded day and its review flags."""
        with self._database.transaction() as conn:
            DayRepository(conn).delete(date.date())
        resp.status = falcon.HTTP_204


class DayRange:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(json=DayRangeInput, resp=Response('HTTP_409', HTTP_200=DayRangeResult), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: DayRangeInput) -> None:
        """Book a full-day type (e.g. PTO) on the work days of a range, or preview it.

        Days off of the schedule, public holidays and company half days are left out. Work days holding times or
        entries are refused (409), skipped or booked too, as `conflicts` says; all days are saved or none.
        """
        with self._database.transaction() as conn:
            resp.media = book_range(conn, json)


def _view(conn: sqlite3.Connection, date: dt.date) -> DayView:
    days = DayRepository(conn)
    return day_view(date, days.get(date), days.flags_on(date), ScheduleRepository(conn).schedules().on(date))


def _flags_by_date(flags: list[ReviewFlag], start: dt.date, end: dt.date) -> defaultdict[dt.date, list[ReviewFlag]]:
    by_date = defaultdict(list)
    for flag in flags:
        if start <= flag.date <= end:
            by_date[flag.date].append(flag)
    return by_date
