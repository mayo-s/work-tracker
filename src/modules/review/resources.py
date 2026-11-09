"""Review endpoints: /api/review and /api/review/counts."""

import datetime as dt
from collections.abc import Callable

import falcon
from spectree import Response

from src.modules.review.schemas import ReviewCounts, ReviewView, review, review_counts
from src.modules.storage.store import Storage
from src.modules.auth.sessions import current_user
from src.utils.spec import spec

TAGS = ['Review']


class Review:
    def __init__(self, storage: Storage, today: Callable[[], dt.date]) -> None:
        self._storage = storage
        self._today = today

    @spec.validate(resp=Response(HTTP_200=ReviewView), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Everything that needs attention; an item disappears once its reason is fixed."""
        with self._storage.transaction() as store:
            resp.media = review(store, current_user(req), self._today())


class ReviewCountsResource:
    def __init__(self, storage: Storage, today: Callable[[], dt.date]) -> None:
        self._storage = storage
        self._today = today

    @spec.validate(resp=Response(HTTP_200=ReviewCounts), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """The number of open review items of each kind, without the items (for the navigation and the dashboard)."""
        with self._storage.transaction() as store:
            resp.media = review_counts(store, current_user(req), self._today())
