"""Export endpoint: /api/export downloads the user's own data as one JSON file (SPEC 5.8)."""

import datetime as dt
from collections.abc import Callable

import falcon
from spectree import Response

from src.modules.auth.sessions import current_user
from src.modules.storage.store import Storage
from src.modules.userdata.export import export_data
from src.modules.userdata.schemas import UserData
from src.utils.spec import spec

TAGS = ['Export and import']


class ExportResource:
    def __init__(self, storage: Storage, clock: Callable[[], dt.datetime] = dt.datetime.now) -> None:
        self._storage = storage
        self._clock = clock

    @spec.validate(resp=Response(HTTP_200=UserData), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """All of your own records as a file to download, e.g. `work-tracker-klara-2026-10-30.json`: settings, work
        schedules, PTO years, services, activity types, tickets, days, entries with their history and review flags.

        Not in it: password, sessions, users, teams and the log of the team view.
        """
        user_id = current_user(req)
        with self._storage.transaction() as store:
            data = export_data(store, user_id, self._clock())
            username = store.users().get(user_id).username
        resp.media = data
        resp.downloadable_as = f'work-tracker-{username}-{data.exported_at.date().isoformat()}.json'
