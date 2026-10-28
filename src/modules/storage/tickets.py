"""Tickets and the service each ticket belongs to."""

import sqlite3
from collections.abc import Iterable

from src.models.catalog import Ticket
from src.modules.storage.errors import ConflictError, NotFoundError


def _key(key: str) -> str:
    """Validated, normalized ticket key (' aga-39 ' → 'AGA-39')."""
    return Ticket(key=key).key


def _sort_key(ticket: Ticket) -> tuple[str, int]:
    prefix, number = ticket.key.rsplit('-', 1)
    return prefix, int(number)


def _to_tickets(rows: Iterable[sqlite3.Row]) -> list[Ticket]:
    return sorted((Ticket(key=row['key'], service_id=row['service_id']) for row in rows), key=_sort_key)


class TicketRepository:
    """Tickets remember their service; works within the transaction of the given connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str) -> Ticket | None:
        row = self._conn.execute('SELECT key, service_id FROM tickets WHERE key = ?', (_key(key),)).fetchone()
        return Ticket(key=row['key'], service_id=row['service_id']) if row else None

    def all(self) -> list[Ticket]:
        """All tickets, sorted by prefix and number (TNG-999 before TNG-5214)."""
        return _to_tickets(self._conn.execute('SELECT key, service_id FROM tickets'))

    def without_service(self) -> list[Ticket]:
        return _to_tickets(self._conn.execute('SELECT key, service_id FROM tickets WHERE service_id IS NULL'))

    def ensure(self, key: str) -> Ticket:
        """The ticket with this key, created without a service if it does not exist yet."""
        self._conn.execute('INSERT INTO tickets (key) VALUES (?) ON CONFLICT (key) DO NOTHING', (_key(key),))
        return self.get(key)

    def set_service(self, key: str, service_id: int | None) -> Ticket:
        self.assign_service([key], service_id)
        return self.get(key)

    def assign_service(self, keys: Iterable[str], service_id: int | None) -> int:
        """Assign one service (or none) to several tickets at once; all tickets must exist. Returns the count."""
        unique = self._existing_keys(keys)
        placeholders = ', '.join('?' for _ in unique)
        try:
            self._conn.execute(f'UPDATE tickets SET service_id = ? WHERE key IN ({placeholders})', (service_id, *unique))
        except sqlite3.IntegrityError as error:
            raise ConflictError(f'Unknown service {service_id}') from error
        return len(unique)

    def _existing_keys(self, keys: Iterable[str]) -> list[str]:
        """Normalized, distinct keys; raises if any ticket does not exist."""
        unique = sorted({_key(key) for key in keys})
        placeholders = ', '.join('?' for _ in unique)
        rows = self._conn.execute(f'SELECT key FROM tickets WHERE key IN ({placeholders})', unique)
        if missing := sorted(set(unique) - {row['key'] for row in rows}):
            raise NotFoundError(f'Unknown tickets: {", ".join(missing)}')
        return unique
