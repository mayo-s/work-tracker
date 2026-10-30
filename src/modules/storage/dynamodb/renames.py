"""Renaming and merging tickets on DynamoDB, with the rules of the SQLite version (renames.py)."""

import datetime as dt
from collections.abc import Callable

from src.models.entries import TicketEntry
from src.models.history import HistoryAction
from src.modules.storage.dynamodb.entries import DynamoEntries
from src.modules.storage.dynamodb.keys import user_partition
from src.modules.storage.dynamodb.tickets import TICKET, DynamoTickets
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.renames import kept_service, new_key_for
from src.modules.storage.store import RenameResult

ITEMS_PER_ENTRY = 3  # the entry, its pointer and its history line


def rename_ticket(
    unit: Unit, user_id: str, old_key: str, new_key: str, clock: Callable[[], dt.datetime] | None = None,
) -> RenameResult:
    """Move all entries of a user's ticket to a new key and delete the old ticket; each moved entry's history records it.

    If the new key already exists, both tickets are merged and the existing ticket keeps its service (it takes the old
    ticket's service only if it has none). Many entries are moved in atomic chunks and the old ticket goes last, so
    repeating a rename that stopped halfway completes it.
    """
    tickets = DynamoTickets(unit, user_id)
    source, target = tickets.get(old_key), tickets.get(new_key)
    new = new_key_for(source, old_key, new_key)
    tickets.ensure(new)
    tickets.set_service(new, kept_service(source, target))
    action = HistoryAction.MERGED if target else HistoryAction.RENAMED
    entries = DynamoEntries(unit, user_id, clock)
    moving = [entry for entry in entries.between(dt.date.min, dt.date.max)
              if isinstance(entry, TicketEntry) and entry.ticket_key == source.key]
    for entry in moving:
        unit.make_room(ITEMS_PER_ENTRY)
        entries.update(entry.model_copy(update={'ticket_key': new}), action)
    unit.delete(user_partition(user_id), TICKET + source.key)
    return RenameResult(tickets.get(new), action, len(moving))
