"""Review endpoints: /api/review, /api/review/counts and clearing review flags."""

import falcon
from spectree import Response

from src.modules.review.schemas import ReviewCounts, ReviewView, review, review_counts
from src.modules.storage.errors import NotFoundError
from src.modules.storage.store import Storage
from src.modules.auth.sessions import current_user
from src.utils.spec import spec

TAGS = ['Review']


class Review:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response(HTTP_200=ReviewView), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Everything that needs attention; an item disappears once its reason is fixed or its flag is cleared."""
        with self._storage.transaction() as store:
            resp.media = review(store, current_user(req))


class ReviewCountsResource:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response(HTTP_200=ReviewCounts), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """The number of open review items of each kind, without the items (for the navigation and the dashboard)."""
        with self._storage.transaction() as store:
            resp.media = review_counts(store, current_user(req))


class ReviewFlagItem:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response('HTTP_204', 'HTTP_404'), tags=TAGS, path_parameter_descriptions={'flag_id': 'Id of the flag'})
    def on_delete(self, req: falcon.Request, resp: falcon.Response, flag_id: str) -> None:
        """Clear a review flag of an entry or a day (e.g. after checking a guessed ticket key)."""
        with self._storage.transaction() as store:
            try:
                store.entries(current_user(req)).clear_flag(flag_id)
            except NotFoundError:
                store.days(current_user(req)).clear_flag(flag_id)
        resp.status = falcon.HTTP_204
