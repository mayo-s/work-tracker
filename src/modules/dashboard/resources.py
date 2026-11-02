"""Dashboard endpoint: /api/dashboard."""

import datetime as dt
from collections.abc import Callable

import falcon
from spectree import Response

from src.modules.dashboard.schemas import Dashboard, DashboardView
from src.modules.storage.store import Storage
from src.modules.teams.view import MemberQuery, viewing
from src.utils.spec import spec


class DashboardResource:
    def __init__(
        self, storage: Storage, today: Callable[[], dt.date], clock: Callable[[], dt.datetime] = dt.datetime.now,
    ) -> None:
        self._storage = storage
        self._today = today
        self._clock = clock

    @spec.validate(query=MemberQuery, resp=Response('HTTP_403', HTTP_200=DashboardView), tags=['Reports'])
    def on_get(self, req: falcon.Request, resp: falcon.Response, query: MemberQuery) -> None:
        """Key figures, the overtime balance over time, days off coming up and this year's figures, up to today; `member`
        shows a member of the team admin's team (team view, logged for the member)."""
        with self._storage.transaction() as store:
            view = viewing(req, store, query.member, self._today())
            view.log(store, 'dashboard', '', self._clock())
            resp.media = Dashboard(store, view.user_id, self._today(), view.stays).view()
