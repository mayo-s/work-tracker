"""Migration 25 (TASKS.md 13.7, SPEC 4.6): entries of one kind, an activity optionally on a ticket.

Rebuilds `entries` without `kind` and `coding`, its `text` as `description` and `activity_type_id` for every entry
(None while the review has to choose one); activity types get `ticket_required`. A user without the activity type an
entry needs (Coding, Meeting) gets it.
"""

import sqlite3

from src.models.base import new_id
from src.models.catalog import new_activity_type
from src.models.former_entries import convert

_COLUMNS = ('id', 'user_id', 'date', 'activity_type_id', 'ticket_key', 'duration', 'description')


def to_one_kind(conn: sqlite3.Connection) -> None:
    conn.execute('ALTER TABLE activity_types ADD COLUMN ticket_required INTEGER NOT NULL DEFAULT 0 '
                 'CHECK (ticket_required IN (0, 1))')
    conn.execute('''CREATE TABLE new_entries (
        id               TEXT NOT NULL PRIMARY KEY,  -- UUIDv7: never reused, so history outlives entries
        user_id          TEXT    NOT NULL,
        date             TEXT    NOT NULL,
        activity_type_id TEXT    REFERENCES activity_types (id),  -- NULL only for former entries awaiting review
        ticket_key       TEXT,
        duration         INTEGER NOT NULL,
        description      TEXT    NOT NULL DEFAULT '',
        FOREIGN KEY (user_id, ticket_key) REFERENCES tickets (user_id, key) ON UPDATE CASCADE
    )''')
    rows = conn.execute('SELECT id, user_id, date, kind, ticket_key, activity_type_id, duration, text, coding FROM entries')
    for row in rows.fetchall():
        former = dict(row) | {'description': row['text'], 'note': row['text']}
        entry = convert(former, lambda name, user=row['user_id']: _activity_type_id(conn, user, name))
        conn.execute(f'INSERT INTO new_entries ({", ".join(_COLUMNS)}) VALUES ({", ".join("?" for _ in _COLUMNS)})',
                     tuple(entry[column] for column in _COLUMNS))
    conn.execute('DROP TABLE entries')
    conn.execute('ALTER TABLE new_entries RENAME TO entries')
    conn.execute('CREATE INDEX entries_by_user_and_date ON entries (user_id, date)')


def _activity_type_id(conn: sqlite3.Connection, user_id: str, name: str) -> str:
    """The user's activity type of that name (ignoring case), added if they do not have it."""
    row = conn.execute('SELECT id FROM activity_types WHERE user_id = ? AND name = ?', (user_id, name)).fetchone()
    if row:
        return row['id']
    added = new_id()
    conn.execute('INSERT INTO activity_types (id, user_id, name, ticket_required) VALUES (?, ?, ?, ?)',
                 (added, user_id, name, new_activity_type(name).ticket_required))
    return added
