"""Renaming and merging tickets, e.g. when reviewing imported ticket keys."""

import datetime as dt
import sqlite3
from collections.abc import Callable
from typing import NamedTuple

from src.models.catalog import Ticket
from src.models.history import HistoryAction
from src.modules.storage.entries import EntryRepository
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.tickets import TicketRepository


class RenameResult(NamedTuple):
    ticket: Ticket
    action: HistoryAction  # renamed, or merged into an existing ticket
    moved: int  # number of entries moved


def rename_ticket(
    conn: sqlite3.Connection, user_id: str, old_key: str, new_key: str, clock: Callable[[], dt.datetime] | None = None
) -> RenameResult:
    """Move all entries of a user's ticket to a new key and delete the old ticket; each moved entry's history records it.

    If the new key already exists, both tickets are merged and the existing ticket keeps its service
    (it takes the old ticket's service only if it has none).
    """
    tickets = TicketRepository(conn, user_id)
    source, target = tickets.get(old_key), tickets.get(new_key)
    new = _new_key(source, old_key, new_key)
    tickets.ensure(new)
    tickets.set_service(new, _kept_service(source, target))
    moved = _move_entries(conn, user_id, source.key, new)
    conn.execute('DELETE FROM tickets WHERE user_id = ? AND key = ?', (user_id, source.key))
    action = HistoryAction.MERGED if target else HistoryAction.RENAMED
    entries = EntryRepository(conn, user_id, clock)
    for entry_id in moved:
        entries.add_history(entry_id, action, {'ticket_key': (source.key, new)})
    return RenameResult(tickets.get(new), action, len(moved))


def _new_key(source: Ticket | None, old_key: str, new_key: str) -> str:
    """The normalized new key; the old ticket must exist and differ from it."""
    if source is None:
        raise NotFoundError(f'Unknown ticket {old_key}')
    new = Ticket(key=new_key).key
    if new == source.key:
        raise ConflictError(f'{source.key} cannot be renamed to itself')
    return new


def _kept_service(source: Ticket, target: Ticket | None) -> int | None:
    """An existing ticket keeps its service; it takes the old ticket's service only if it has none."""
    if target and target.service_id is not None:
        return target.service_id
    return source.service_id


def _move_entries(conn: sqlite3.Connection, user_id: str, old_key: str, new_key: str) -> list[int]:
    """Move all of the user's entries from the old to the new key; returns the ids of the moved entries."""
    moved = [row['id'] for row in conn.execute('SELECT id FROM entries WHERE user_id = ? AND ticket_key = ? ORDER BY id',
                                               (user_id, old_key))]
    conn.execute('UPDATE entries SET ticket_key = ? WHERE user_id = ? AND ticket_key = ?', (new_key, user_id, old_key))
    return moved
