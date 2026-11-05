"""Search endpoint: /api/search."""

import datetime as dt
from collections.abc import Callable

import falcon
from spectree import Response

from src.modules.auth.sessions import current_user
from src.modules.search.schemas import SearchQuery, SearchResult, search
from src.modules.storage.store import Storage
from src.utils.spec import spec


class SearchResource:
    def __init__(self, storage: Storage, today: Callable[[], dt.date]) -> None:
        self._storage = storage
        self._today = today

    @spec.validate(query=SearchQuery, resp=Response(HTTP_200=SearchResult), tags=['Search'])
    def on_get(self, req: falcon.Request, resp: falcon.Response, query: SearchQuery) -> None:
        """Find entries of a period (default: this year) by text, service or activity type: their hours and number,
        by ticket or activity type and by month, and the entries themselves."""
        with self._storage.transaction() as store:
            resp.media = search(store, current_user(req), query, self._today())
