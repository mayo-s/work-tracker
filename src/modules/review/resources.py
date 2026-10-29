"""Review endpoints: /api/review and clearing review flags."""

import falcon
from spectree import Response

from src.modules.review.schemas import ReviewView, review
from src.modules.storage.database import Database
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.errors import NotFoundError
from src.modules.auth.sessions import current_user
from src.utils.spec import spec

TAGS = ['Review']


class Review:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response(HTTP_200=ReviewView), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Everything that needs attention; an item disappears once its reason is fixed or its flag is cleared."""
        with self._database.transaction() as conn:
            resp.media = review(conn, current_user(req))


class ReviewFlagItem:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response('HTTP_204', 'HTTP_404'), tags=TAGS, path_parameter_descriptions={'flag_id': 'Id of the flag'})
    def on_delete(self, req: falcon.Request, resp: falcon.Response, flag_id: int) -> None:
        """Clear a review flag of an entry or a day (e.g. after checking a guessed ticket key)."""
        with self._database.transaction() as conn:
            try:
                EntryRepository(conn, current_user(req)).clear_flag(flag_id)
            except NotFoundError:
                DayRepository(conn, current_user(req)).clear_flag(flag_id)
        resp.status = falcon.HTTP_204
