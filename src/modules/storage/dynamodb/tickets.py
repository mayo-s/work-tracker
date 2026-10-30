"""Tickets in a user's partition (`TICKET#<key>`, with the service); so far what entries need: a ticket on first use."""

from src.models.catalog import Ticket
from src.modules.storage.dynamodb.table import attributes
from src.modules.storage.dynamodb.unit import Unit

TICKET = 'TICKET#'


def ensure_ticket(unit: Unit, pk: str, key: str) -> Ticket:
    """The ticket with this key (normalized, e.g. ' aga-39 ' → AGA-39), created without a service if it is new."""
    ticket = Ticket(key=key)
    if stored := unit.get(pk, TICKET + ticket.key):
        return Ticket(**attributes(stored))
    unit.put({'PK': pk, 'SK': TICKET + ticket.key, **ticket.model_dump()})
    return ticket
