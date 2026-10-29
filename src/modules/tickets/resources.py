"""Tickets endpoints: list, service per ticket (also for several at once), rename and merge."""

import sqlite3

import falcon
from pydantic import ValidationError
from spectree import Response

from src.models.catalog import Ticket
from src.modules.storage.database import Database
from src.modules.storage.renames import rename_ticket
from src.modules.storage.tickets import TicketRepository
from src.modules.tickets.schemas import (
    AssignmentResult,
    RenameView,
    ServiceAssignment,
    TicketQuery,
    TicketRename,
    TicketServiceInput,
    TicketView,
    ticket_views,
)
from src.modules.auth.sessions import current_user
from src.utils.spec import spec

TAGS = ['Tickets']
KEY_PARAMETER = {'key': 'Ticket key, e.g. ENGINE-461 (case-insensitive)'}


class TicketCollection:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(query=TicketQuery, resp=Response(HTTP_200=list[TicketView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response, query: TicketQuery) -> None:
        """All tickets (sorted by prefix and number) with their service and number of entries."""
        with self._database.transaction() as conn:
            user_id = current_user(req)
            tickets = TicketRepository(conn, user_id)
            resp.media = ticket_views(conn, user_id, tickets.without_service() if query.without_service else tickets.all())


class TicketItem:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response('HTTP_404', HTTP_200=TicketView), tags=TAGS, path_parameter_descriptions=KEY_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, key: str) -> None:
        """A known ticket with the service it remembers (used to pre-fill the service of a new entry)."""
        with self._database.transaction() as conn:
            user_id = current_user(req)
            resp.media = ticket_views(conn, user_id, [_existing(conn, user_id, key)])[0]

    @spec.validate(json=TicketServiceInput, resp=Response('HTTP_404', 'HTTP_409', HTTP_200=TicketView), tags=TAGS,
                   path_parameter_descriptions=KEY_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, key: str, json: TicketServiceInput) -> None:
        """Set or unassign the service of a ticket; it applies to all entries of the ticket."""
        with self._database.transaction() as conn:
            user_id = current_user(req)
            ticket = TicketRepository(conn, user_id).set_service(_existing(conn, user_id, key).key, json.service_id)
            resp.media = ticket_views(conn, user_id, [ticket])[0]


class TicketServiceAssignment:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(json=ServiceAssignment, resp=Response('HTTP_404', 'HTTP_409', HTTP_200=AssignmentResult), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: ServiceAssignment) -> None:
        """Assign one service to several tickets at once; if a ticket is unknown, nothing changes."""
        with self._database.transaction() as conn:
            assigned = TicketRepository(conn, current_user(req)).assign_service(json.keys, json.service_id)
            resp.media = AssignmentResult(assigned=assigned)


class TicketRenaming:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(json=TicketRename, resp=Response('HTTP_404', 'HTTP_409', HTTP_200=RenameView), tags=TAGS,
                   path_parameter_descriptions=KEY_PARAMETER)
    def on_post(self, req: falcon.Request, resp: falcon.Response, key: str, json: TicketRename) -> None:
        """Rename a ticket, or merge it into an existing one (which keeps its service); recorded in each entry's history."""
        with self._database.transaction() as conn:
            user_id = current_user(req)
            result = rename_ticket(conn, user_id, _existing(conn, user_id, key).key, json.new_key)
            resp.media = RenameView(ticket=ticket_views(conn, user_id, [result.ticket])[0], action=result.action,
                                    moved=result.moved)


def _existing(conn: sqlite3.Connection, user_id: int, key: str) -> Ticket:
    """The user's ticket with this key; 404 for unknown or invalid keys."""
    try:
        ticket = TicketRepository(conn, user_id).get(key)
    except ValidationError:
        ticket = None
    if ticket is None:
        raise falcon.HTTPNotFound(description=f'Unknown ticket {key}')
    return ticket
