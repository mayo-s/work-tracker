"""Days endpoints: /api/days, /api/days/{date} and /api/days/range."""

import datetime as dt

import falcon
from spectree import Response

from src.lib.dates import each_day
from src.modules.days.ranges import DayRangeInput, DayRangeResult, book_range
from src.modules.days.schemas import DayInput, DayView, day_view, team_view_day
from src.modules.auth.sessions import current_user
from src.modules.storage.store import Storage, Store
from src.modules.teams.view import MemberPeriodQuery, viewing
from src.utils.spec import spec

TAGS = ['Days']
DATE_PARAMETER = {'date': 'Date in ISO format, e.g. 2026-10-28'}


class DayCollection:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(query=MemberPeriodQuery, resp=Response('HTTP_403', HTTP_200=list[DayView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response, query: MemberPeriodQuery) -> None:
        """Every calendar day of a week or date range, recorded or not; `member` shows a member of the team admin's team
        (team view: no notes; days before they joined the team without data)."""
        start, end = query.period()
        with self._storage.transaction() as store:
            view = viewing(req, store, query.member)
            days = store.days(view.user_id)
            recorded = {day.date: day for day in days.between(start, end)}
            schedules = store.schedules(view.user_id).schedules()
        shown = [day_view(date, recorded.get(date), schedules.on(date)) for date in each_day(start, end)]
        resp.media = [team_view_day(day, view.stays) for day in shown] if view.stays else shown


class DayItem:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response(HTTP_200=DayView), tags=TAGS, path_parameter_descriptions=DATE_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, date: dt.datetime) -> None:
        """One calendar day, recorded or not."""
        with self._storage.transaction() as store:
            resp.media = _view(store, current_user(req), date.date())

    @spec.validate(json=DayInput, resp=Response(HTTP_200=DayView), tags=TAGS, path_parameter_descriptions=DATE_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, date: dt.datetime, json: DayInput) -> None:
        """Record a day (insert or replace)."""
        with self._storage.transaction() as store:
            store.days(current_user(req)).save(json.to_day(date.date()))
            resp.media = _view(store, current_user(req), date.date())

    @spec.validate(resp=Response('HTTP_204', 'HTTP_404'), tags=TAGS, path_parameter_descriptions=DATE_PARAMETER)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, date: dt.datetime) -> None:
        """Delete a recorded day."""
        with self._storage.transaction() as store:
            store.days(current_user(req)).delete(date.date())
        resp.status = falcon.HTTP_204


class DayRange:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(json=DayRangeInput, resp=Response('HTTP_409', HTTP_200=DayRangeResult), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: DayRangeInput) -> None:
        """Book a full-day type (e.g. PTO) on the work days of a range, or preview it.

        Days off of the schedule, public holidays and company half days are left out. Work days holding times or
        entries are refused (409), skipped or booked too, as `conflicts` says; all days are saved or none.
        """
        with self._storage.transaction() as store:
            resp.media = book_range(store, current_user(req), json)


def _view(store: Store, user_id: str, date: dt.date) -> DayView:
    return day_view(date, store.days(user_id).get(date), store.schedules(user_id).schedules().on(date))
