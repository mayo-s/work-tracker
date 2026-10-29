"""Dashboard endpoint: /api/dashboard."""

import datetime as dt
from collections.abc import Callable

import falcon
from spectree import Response

from src.modules.dashboard.schemas import Dashboard, DashboardView
from src.modules.storage.database import Database
from src.modules.teams.view import MemberQuery, viewing
from src.utils.spec import spec


class DashboardResource:
    def __init__(
        self, database: Database, today: Callable[[], dt.date], clock: Callable[[], dt.datetime] = dt.datetime.now,
    ) -> None:
        self._database = database
        self._today = today
        self._clock = clock

    @spec.validate(query=MemberQuery, resp=Response('HTTP_403', HTTP_200=DashboardView), tags=['Reports'])
    def on_get(self, req: falcon.Request, resp: falcon.Response, query: MemberQuery) -> None:
        """Key figures, the overtime balance over time, days off coming up and this year's figures, up to today; `member`
        shows a member of the team admin's team (team view, logged for the member)."""
        with self._database.transaction() as conn:
            view = viewing(req, conn, query.member)
            view.log(conn, 'dashboard', '', self._clock())
            resp.media = Dashboard(conn, view.user_id, self._today(), view.visible_from).view()
