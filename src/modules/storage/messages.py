"""The messages of the contact page and their changes on SQLite (SPEC 5.14); works within the transaction of the given
connection."""

import datetime as dt
import sqlite3

from src.models.base import new_id
from src.models.messages import SUPPORT, ContactMessage, MessageChange
from src.modules.storage.errors import NotFoundError

_MESSAGE = 'id, sent_at, name, email, subject, text, user_id, status, done_at, anonymized'
_CHANGES = ("SELECT message_changes.id, message_id, at, actor_id, kind, detail,"
            f" COALESCE(trim(first_name || ' ' || last_name), '{SUPPORT}') AS actor_name"
            ' FROM message_changes LEFT JOIN users ON users.id = actor_id')


def _iso(moment: dt.datetime | None) -> str | None:
    return moment.isoformat() if moment else None


class MessageRepository:
    """Messages newest first, each with its changes (status, notes) oldest first; for support."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, message: ContactMessage) -> ContactMessage:
        added = message.model_copy(update={'id': new_id()})
        self.restore(added)
        return added

    def get(self, message_id: str) -> ContactMessage:
        row = self._conn.execute(f'SELECT {_MESSAGE} FROM contact_messages WHERE id = ?', (message_id,)).fetchone()
        if row is None:
            raise NotFoundError(f'No message with id {message_id}')
        return ContactMessage(**dict(row))

    def all(self) -> list[ContactMessage]:
        """All messages, newest first (the ids start with the time they came)."""
        rows = self._conn.execute(f'SELECT {_MESSAGE} FROM contact_messages ORDER BY sent_at DESC, id DESC')
        return [ContactMessage(**dict(row)) for row in rows]

    def save(self, message: ContactMessage) -> ContactMessage:
        """Its status, when it was last marked Done, and the sender (anonymized)."""
        cursor = self._conn.execute(
            'UPDATE contact_messages SET name = ?, email = ?, user_id = ?, status = ?, done_at = ?, anonymized = ?'
            ' WHERE id = ?', (message.name, message.email, message.user_id, message.status, _iso(message.done_at),
                              int(message.anonymized), message.id))
        if not cursor.rowcount:
            raise NotFoundError(f'No message with id {message.id}')
        return self.get(message.id)

    def delete(self, message_id: str) -> None:
        """The message with its changes."""
        self.get(message_id)  # 404 for an unknown one
        self._conn.execute('DELETE FROM message_changes WHERE message_id = ?', (message_id,))
        self._conn.execute('DELETE FROM contact_messages WHERE id = ?', (message_id,))

    def add_change(self, change: MessageChange) -> MessageChange:
        self.get(change.message_id)  # 404 for an unknown message
        added = change.model_copy(update={'id': new_id()})
        self.restore_change(added)
        return next(item for item in self.changes(change.message_id) if item.id == added.id)

    def changes(self, message_id: str) -> list[MessageChange]:
        """The message's changes, oldest first, with the names of who made them ("Support" once anonymized)."""
        rows = self._conn.execute(f'{_CHANGES} WHERE message_id = ? ORDER BY at, message_changes.id', (message_id,))
        return [MessageChange(**dict(row)) for row in rows]

    def all_changes(self) -> list[MessageChange]:
        """All changes of all messages, oldest first (for the search and the full backup)."""
        return [MessageChange(**dict(row)) for row in self._conn.execute(f'{_CHANGES} ORDER BY at, message_changes.id')]

    def anonymize(self, message_id: str, name: str) -> ContactMessage:
        """The sender becomes `name` (a color and an animal) without e-mail address or account, and who made its
        changes becomes "Support"; subject, text and notes stay."""
        message = self.get(message_id)
        self._conn.execute('UPDATE message_changes SET actor_id = NULL WHERE message_id = ?', (message_id,))
        return self.save(message.model_copy(update={'name': name, 'email': '', 'user_id': None, 'anonymized': True}))

    def restore(self, message: ContactMessage) -> None:
        """A message as it was, with its id (also for the full backup)."""
        self._conn.execute(f'INSERT INTO contact_messages ({_MESSAGE}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                           (message.id, message.sent_at.isoformat(), message.name, message.email, message.subject,
                            message.text, message.user_id, message.status, _iso(message.done_at), int(message.anonymized)))

    def restore_change(self, change: MessageChange) -> None:
        """A change as it was, with its id (also for the full backup)."""
        self._conn.execute('INSERT INTO message_changes (id, message_id, at, actor_id, kind, detail)'
                           ' VALUES (?, ?, ?, ?, ?, ?)',
                           (change.id, change.message_id, change.at.isoformat(), change.actor_id, change.kind, change.detail))
