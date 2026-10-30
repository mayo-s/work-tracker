"""Tickets in a user's partition (`TICKET#<key>`, with the service), as the SQLite repository (tickets.py)."""

from collections import Counter
from collections.abc import Iterable

from src.models.catalog import Ticket
from src.modules.storage.dynamodb.catalog import service_key
from src.modules.storage.dynamodb.keys import user_partition
from src.modules.storage.dynamodb.table import attributes
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.tickets import ticket_order

TICKET = 'TICKET#'


def ensure_ticket(unit: Unit, pk: str, key: str) -> Ticket:
    """The ticket with this key (normalized, e.g. ' aga-39 ' → AGA-39), created without a service if it is new."""
    ticket = Ticket(key=key)
    if stored := unit.get(pk, TICKET + ticket.key):
        return Ticket(**attributes(stored))
    unit.put({'PK': pk, 'SK': TICKET + ticket.key, **ticket.model_dump()})
    return ticket


class DynamoTickets:
    """Tickets of one user remember their service."""

    def __init__(self, unit: Unit, user_id: str) -> None:
        self._unit = unit
        self._pk = user_partition(user_id)

    def get(self, key: str) -> Ticket | None:
        item = self._unit.get(self._pk, TICKET + Ticket(key=key).key)
        return Ticket(**attributes(item)) if item else None

    def all(self) -> list[Ticket]:
        """All tickets, sorted by prefix and number (TNG-999 before TNG-5214)."""
        return sorted((Ticket(**attributes(item)) for item in self._unit.query_prefix(self._pk, TICKET)), key=ticket_order)

    def without_service(self) -> list[Ticket]:
        return [ticket for ticket in self.all() if ticket.service_id is None]

    def entry_counts(self) -> dict[str, int]:
        """Number of entries per ticket key (tickets without entries are missing)."""
        return dict(Counter(entry['ticket_key'] for entry in self._unit.query_prefix(self._pk, 'ENTRY#')
                            if entry.get('ticket_key')))

    def ensure(self, key: str) -> Ticket:
        """The ticket with this key, created without a service if it does not exist yet."""
        return ensure_ticket(self._unit, self._pk, key)

    def set_service(self, key: str, service_id: int | None) -> Ticket:
        self.assign_service([key], service_id)
        return self.get(key)

    def assign_service(self, keys: Iterable[str], service_id: int | None) -> int:
        """Assign one service (or none) to several tickets at once; all tickets must exist. Returns the count.

        More than fit into one transaction are written in chunks; each ticket on its own is right after each chunk.
        """
        tickets = self._existing(keys)
        if service_id is not None and self._unit.get(self._pk, service_key(service_id)) is None:
            raise ConflictError(f'Unknown service {service_id}')
        for ticket in tickets:
            self._unit.make_room(1)
            self._unit.put({'PK': self._pk, 'SK': TICKET + ticket.key, **ticket.model_dump(), 'service_id': service_id})
        return len(tickets)

    def _existing(self, keys: Iterable[str]) -> list[Ticket]:
        """The tickets of the normalized, distinct keys; raises if any does not exist."""
        unique = sorted({Ticket(key=key).key for key in keys})
        found = {key: self.get(key) for key in unique}
        if missing := [key for key, ticket in found.items() if ticket is None]:
            raise NotFoundError(f'Unknown tickets: {", ".join(missing)}')
        return list(found.values())
