"""The contact page's endpoint: /api/contact, open to everyone like the page /contact (SPEC 5.14)."""

import datetime as dt
from collections.abc import Callable

import falcon
from spectree import Response

from src.models.messages import ContactMessage
from src.modules.contact.schemas import ContactInput
from src.modules.storage.store import Storage, Store
from src.modules.support.archive import archive_due
from src.utils.spec import spec

TAGS = ['Contact']
VISITOR_MESSAGES = 5  # within the pause, from visitors who are not logged in
VISITOR_PAUSE = dt.timedelta(minutes=10)
TOO_MANY = 'Too many messages; try again in a few minutes'


class ContactResource:
    def __init__(self, storage: Storage, clock: Callable[[], dt.datetime]) -> None:
        self._storage = storage
        self._clock = clock

    @spec.validate(json=ContactInput, resp=Response('HTTP_201', 'HTTP_429'), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: ContactInput) -> None:
        """Send a message to support, who answer by e-mail; a logged-in user's is linked to their account.

        A message with the hidden field filled in (a bot) is dropped, though it answers 201 like any other. Messages from
        visitors who are not logged in pause after 5 within 10 minutes (429).
        """
        resp.status = falcon.HTTP_201
        if json.website:
            return
        user_id, now = req.context.get('user_id'), self._clock()
        with self._storage.transaction() as store:
            if user_id is None and _visitor_messages(store, now) >= VISITOR_MESSAGES:
                raise falcon.HTTPTooManyRequests(description=TOO_MANY)
            store.messages().add(ContactMessage(sent_at=now, user_id=user_id,
                                                **json.model_dump(include={'name', 'email', 'subject', 'text'})))
            archive_due(store, now)  # the app has no timer: done messages are archived when the next one comes


def _visitor_messages(store: Store, now: dt.datetime) -> int:
    """The messages of visitors who were not logged in, within the pause."""
    since = now - VISITOR_PAUSE
    return sum(1 for message in store.messages().all() if message.user_id is None and message.sent_at > since
               and not message.anonymized)
