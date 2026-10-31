"""Entries endpoints: /api/entries, /api/entries/{entry_id} and its history."""


import falcon
from spectree import Response

from src.modules.entries.schemas import ChangeView, EntryInput, EntrySplitInput, EntryView, EntryViewer
from src.modules.auth.sessions import current_user
from src.modules.storage.errors import NotFoundError
from src.modules.storage.store import Storage, Store
from src.modules.teams.view import MemberPeriodQuery, viewing
from src.utils.spec import spec

TAGS = ['Entries']
ID_PARAMETER = {'entry_id': 'Id of the entry'}


class EntryCollection:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(query=MemberPeriodQuery, resp=Response('HTTP_403', HTTP_200=list[EntryView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response, query: MemberPeriodQuery) -> None:
        """Entries of a week or date range, by date and in the order they were created; `member` shows a member of the
        team admin's team (team view: from the day they joined the team)."""
        start, end = query.period()
        with self._storage.transaction() as store:
            view = viewing(req, store, query.member)
            entries = store.entries(view.user_id).between(max(start, view.visible_from or start), end)
            resp.media = EntryViewer(store, view.user_id).views(entries)

    @spec.validate(json=EntryInput, resp=Response('HTTP_409', HTTP_201=EntryView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: EntryInput) -> None:
        """Create an entry; a new ticket is created, `service_id` sets the ticket's service. The duration takes e.g.
        `1:30`, `1.5`, `1h30m` or `90m`, in quarter hours, at most the rest of the day from its start (409)."""
        with self._storage.transaction() as store:
            view = _save(store, current_user(req), json)
        resp.status = falcon.HTTP_201
        resp.location = f'{req.path}/{view.id}'
        resp.media = view


class EntryItem:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response('HTTP_404', HTTP_200=EntryView), tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, entry_id: str) -> None:
        """One entry."""
        with self._storage.transaction() as store:
            user_id = current_user(req)
            resp.media = EntryViewer(store, user_id).view(store.entries(user_id).get(entry_id))

    @spec.validate(json=EntryInput, resp=Response('HTTP_404', 'HTTP_409', HTTP_200=EntryView), tags=TAGS,
                   path_parameter_descriptions=ID_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, entry_id: str, json: EntryInput) -> None:
        """Change an entry; only changed fields are written to its history. The kind cannot change."""
        with self._storage.transaction() as store:
            resp.media = _save(store, current_user(req), json, entry_id)

    @spec.validate(resp=Response('HTTP_204', 'HTTP_404'), tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, entry_id: str) -> None:
        """Delete an entry and its review flags; its history is kept."""
        with self._storage.transaction() as store:
            store.entries(current_user(req)).delete(entry_id)
        resp.status = falcon.HTTP_204


class EntrySplit:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(json=EntrySplitInput, resp=Response('HTTP_404', 'HTTP_409', HTTP_200=list[EntryView]), tags=TAGS,
                   path_parameter_descriptions=ID_PARAMETER)
    def on_post(self, req: falcon.Request, resp: falcon.Response, entry_id: str, json: EntrySplitInput) -> None:
        """Divide a ticket entry among several tickets (e.g. an alias like #4347 aka #1482), hours split evenly."""
        with self._storage.transaction() as store:
            user_id = current_user(req)
            resp.media = EntryViewer(store, user_id).views(store.entries(user_id).split(entry_id, json.ticket_keys))


class EntryHistory:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response('HTTP_404', HTTP_200=list[ChangeView]), tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, entry_id: str) -> None:
        """The history of an entry, oldest first; also available after the entry was deleted. An entry the user never
        had (unknown, or another user's) answers 404."""
        with self._storage.transaction() as store:
            changes = store.entries(current_user(req)).history(entry_id)
        if not changes:
            raise NotFoundError(f'No entry with id {entry_id}')
        resp.media = [ChangeView(**change.model_dump()) for change in changes]


def _save(store: Store, user_id: str, json: EntryInput, entry_id: str | None = None) -> EntryView:
    entries = store.entries(user_id)
    entries.check_fits_day(json.to_entry(entry_id))
    entry = entries.create(json.to_entry()) if entry_id is None else entries.update(json.to_entry(entry_id))
    if json.sets_service:
        store.tickets(user_id).set_service(entry.ticket_key, json.service_id)
    return EntryViewer(store, user_id).view(entry)
