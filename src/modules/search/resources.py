"""Search endpoint: /api/search."""

import falcon
from spectree import Response

from src.modules.auth.sessions import current_user
from src.modules.search.schemas import SearchQuery, SearchResult, search
from src.modules.storage.store import Storage
from src.utils.spec import spec


class SearchResource:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(query=SearchQuery, resp=Response(HTTP_200=SearchResult), tags=['Search'])
    def on_get(self, req: falcon.Request, resp: falcon.Response, query: SearchQuery) -> None:
        """Find entries of all time or a period by text, service or activity type: their hours and number, by ticket or
        activity type and by month, and the entries themselves (with `limit` only the newest)."""
        with self._storage.transaction() as store:
            resp.media = search(store, current_user(req), query)
