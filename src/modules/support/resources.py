"""The support page's endpoints: the contact messages with their status, notes and archive, for support users only
(SPEC 5.14)."""

import datetime as dt
from collections import defaultdict
from collections.abc import Callable

import falcon
from spectree import Response

from src.lib.texts import text
from src.models.messages import ContactMessage, MessageChange
from src.models.users import User
from src.modules.auth.sessions import current_user
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.store import Storage, Store
from src.modules.support.archive import archive_due
from src.modules.support.schemas import MessageView, NoteInput, StatusInput, SupportMessages, SupportQuery
from src.utils.spec import spec

TAGS = ['Support']
ID_PARAMETER = {'message_id': 'Id of the message'}
ARCHIVED = text('An archived message stays as it is; it can only be deleted')


def _support(req: falcon.Request, store: Store) -> User:
    """The current user if they are support; 403 otherwise."""
    try:
        user = store.users().get(current_user(req))
    except NotFoundError:  # e.g. no user yet with the login off
        user = None
    if user is None or not user.support:
        raise falcon.HTTPForbidden(description=text('Only support reads the contact messages'))
    return user


def _views(store: Store, messages: list[ContactMessage]) -> list[MessageView]:
    """The messages with the senders' usernames and their changes."""
    usernames = {user.id: user.username for user in store.users().all()}
    changes: dict[str, list[MessageChange]] = defaultdict(list)
    for change in store.messages().all_changes():
        changes[change.message_id].append(change)
    return [MessageView.of(message, usernames.get(message.user_id), changes[message.id]) for message in messages]


def _matches(view: MessageView, words: list[str]) -> bool:
    """All words are in the subject, the message or a note, ignoring case."""
    notes = (change.detail for change in view.changes if change.kind == 'note')
    found = ' '.join((view.subject, view.text, *notes)).casefold()
    return all(word in found for word in words)


def _found(views: list[MessageView], text: str) -> SupportMessages:
    """The messages that match the words of `text`, apart from the archived ones."""
    words, lists = text.casefold().split(), SupportMessages(messages=[], archive=[])
    for view in views:
        if _matches(view, words):
            (lists.archive if view.archived else lists.messages).append(view)
    return lists


class _SupportResource:
    def __init__(self, storage: Storage, clock: Callable[[], dt.datetime]) -> None:
        self._storage = storage
        self._clock = clock


class SupportMessageCollection(_SupportResource):
    @spec.validate(query=SupportQuery, resp=Response('HTTP_403', HTTP_200=SupportMessages), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response, query: SupportQuery) -> None:
        """The messages and the archive, newest first, each with its changes; with `text` only those that match. First
        archives the messages done for 90 days (the app has no timer)."""
        with self._storage.transaction() as store:
            _support(req, store)
            archive_due(store, self._clock())
            resp.media = _found(_views(store, store.messages().all()), query.text)


class SupportMessageItem(_SupportResource):
    @spec.validate(resp=Response('HTTP_403', 'HTTP_404', HTTP_200=MessageView), tags=TAGS,
                   path_parameter_descriptions=ID_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, message_id: str) -> None:
        """One message with its changes."""
        with self._storage.transaction() as store:
            _support(req, store)
            resp.media = _views(store, [store.messages().get(message_id)])[0]

    @spec.validate(json=StatusInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_200=MessageView), tags=TAGS,
                   path_parameter_descriptions=ID_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, message_id: str, json: StatusInput) -> None:
        """Set the status (kept in its changes); Done also when it was marked so, which starts the 90 days until the
        archive. An archived message stays as it is (409)."""
        with self._storage.transaction() as store:
            user, messages = _support(req, store), store.messages()
            message, now = _changeable(store, message_id), self._clock()
            if json.status != message.status:
                done_at = now if json.status == 'done' else message.done_at
                messages.save(message.model_copy(update={'status': json.status, 'done_at': done_at}))
                messages.add_change(MessageChange(message_id=message_id, at=now, actor_id=user.id, kind='status',
                                                  detail=json.status))
            resp.media = _views(store, [messages.get(message_id)])[0]

    @spec.validate(resp=Response('HTTP_204', 'HTTP_403', 'HTTP_404'), tags=TAGS,
                   path_parameter_descriptions=ID_PARAMETER)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, message_id: str) -> None:
        """Delete a message with its changes, also an archived one."""
        with self._storage.transaction() as store:
            _support(req, store)
            store.messages().delete(message_id)
        resp.status = falcon.HTTP_204


class SupportMessageNotes(_SupportResource):
    @spec.validate(json=NoteInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_201=MessageView), tags=TAGS,
                   path_parameter_descriptions=ID_PARAMETER)
    def on_post(self, req: falcon.Request, resp: falcon.Response, message_id: str, json: NoteInput) -> None:
        """Add an internal note, which only support sees. An archived message stays as it is (409)."""
        with self._storage.transaction() as store:
            user = _support(req, store)
            _changeable(store, message_id)
            store.messages().add_change(MessageChange(message_id=message_id, at=self._clock(), actor_id=user.id,
                                                      kind='note', detail=json.text))
            resp.media = _views(store, [store.messages().get(message_id)])[0]
        resp.status = falcon.HTTP_201


def _changeable(store: Store, message_id: str) -> ContactMessage:
    """The message, unless it is archived (409)."""
    message = store.messages().get(message_id)
    if message.anonymized:
        raise ConflictError(ARCHIVED)
    return message
