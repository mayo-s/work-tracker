"""Dashboard endpoint: /api/dashboard."""

import datetime as dt
from collections.abc import Callable

import falcon
from spectree import Response

from src.modules.dashboard.schemas import Dashboard, DashboardView
from src.modules.storage.database import Database
from src.modules.auth.sessions import current_user
from src.utils.spec import spec


class DashboardResource:
    def __init__(self, database: Database, today: Callable[[], dt.date]) -> None:
        self._database = database
        self._today = today

    @spec.validate(resp=Response(HTTP_200=DashboardView), tags=['Reports'])
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Key figures, the overtime balance over time, days off coming up and this year's figures, up to today."""
        with self._database.transaction() as conn:
            resp.media = Dashboard(conn, current_user(req), self._today()).view()
