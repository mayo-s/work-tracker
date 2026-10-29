"""Entries endpoints: /api/entries, /api/entries/{entry_id} and its history."""

import sqlite3

import falcon
from spectree import Response

from src.modules.entries.schemas import ChangeView, EntryInput, EntrySplitInput, EntryView, EntryViewer
from src.modules.storage.database import Database
from src.modules.storage.entries import EntryRepository
from src.modules.storage.tickets import TicketRepository
from src.utils.api import PeriodQuery
from src.modules.auth.sessions import current_user
from src.utils.spec import spec

TAGS = ['Entries']
ID_PARAMETER = {'entry_id': 'Id of the entry'}


class EntryCollection:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(query=PeriodQuery, resp=Response(HTTP_200=list[EntryView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response, query: PeriodQuery) -> None:
        """Entries of a week or date range, by date and in the order they were created."""
        with self._database.transaction() as conn:
            user_id = current_user(req)
            resp.media = EntryViewer(conn, user_id).views(EntryRepository(conn, user_id).between(*query.period()))

    @spec.validate(json=EntryInput, resp=Response('HTTP_409', HTTP_201=EntryView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: EntryInput) -> None:
        """Create an entry; a new ticket is created, `service_id` sets the ticket's service."""
        with self._database.transaction() as conn:
            view = _save(conn, current_user(req), json)
        resp.status = falcon.HTTP_201
        resp.location = f'{req.path}/{view.id}'
        resp.media = view


class EntryItem:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response('HTTP_404', HTTP_200=EntryView), tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, entry_id: int) -> None:
        """One entry."""
        with self._database.transaction() as conn:
            user_id = current_user(req)
            resp.media = EntryViewer(conn, user_id).view(EntryRepository(conn, user_id).get(entry_id))

    @spec.validate(json=EntryInput, resp=Response('HTTP_404', 'HTTP_409', HTTP_200=EntryView), tags=TAGS,
                   path_parameter_descriptions=ID_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, entry_id: int, json: EntryInput) -> None:
        """Change an entry; only changed fields are written to its history. The kind cannot change."""
        with self._database.transaction() as conn:
            resp.media = _save(conn, current_user(req), json, entry_id)

    @spec.validate(resp=Response('HTTP_204', 'HTTP_404'), tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, entry_id: int) -> None:
        """Delete an entry and its review flags; its history is kept."""
        with self._database.transaction() as conn:
            EntryRepository(conn, current_user(req)).delete(entry_id)
        resp.status = falcon.HTTP_204


class EntrySplit:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(json=EntrySplitInput, resp=Response('HTTP_404', 'HTTP_409', HTTP_200=list[EntryView]), tags=TAGS,
                   path_parameter_descriptions=ID_PARAMETER)
    def on_post(self, req: falcon.Request, resp: falcon.Response, entry_id: int, json: EntrySplitInput) -> None:
        """Divide a ticket entry among several tickets (e.g. an alias like #4347 aka #1482), hours split evenly."""
        with self._database.transaction() as conn:
            user_id = current_user(req)
            resp.media = EntryViewer(conn, user_id).views(EntryRepository(conn, user_id).split(entry_id, json.ticket_keys))


class EntryHistory:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response(HTTP_200=list[ChangeView]), tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, entry_id: int) -> None:
        """The history of an entry, oldest first; also available after the entry was deleted."""
        with self._database.transaction() as conn:
            changes = EntryRepository(conn, current_user(req)).history(entry_id)
            resp.media = [ChangeView(**change.model_dump()) for change in changes]


def _save(conn: sqlite3.Connection, user_id: int, json: EntryInput, entry_id: int | None = None) -> EntryView:
    entries = EntryRepository(conn, user_id)
    entry = entries.create(json.to_entry()) if entry_id is None else entries.update(json.to_entry(entry_id))
    if json.sets_service:
        TicketRepository(conn, user_id).set_service(entry.ticket_key, json.service_id)
    return EntryViewer(conn, user_id).view(entry)
