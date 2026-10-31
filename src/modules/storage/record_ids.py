"""Migration 13 (SPEC 7.2a): records get UUIDv7 ids instead of integers counting up.

The new ids keep the order of the old ones, and every reference follows: tickets (service), entries (activity type),
history lines (entry, the activity types in their changes, "Split from entry …"), review flags (entry), services and
memberships and invitations (team). Entries known only from their history (deleted ones) get ids too.
"""

import json
import re
import sqlite3
from collections.abc import Callable, Iterable

from src.models.base import new_id

Ids = dict[int, str]  # old id → new id
_SPLIT_FROM = re.compile(r'Split from entry (\d+)')

_SCHEMA = {
    'activity_types': '''(
        id      TEXT NOT NULL PRIMARY KEY,
        user_id TEXT NOT NULL,
        name    TEXT NOT NULL COLLATE NOCASE,
        UNIQUE (user_id, name)
    )''',
    'teams': '''(
        id         TEXT NOT NULL PRIMARY KEY,
        name       TEXT NOT NULL COLLATE NOCASE,
        deleted_at TEXT  -- deleted teams stay for the membership history
    )''',
    'services': '''(
        id         TEXT NOT NULL PRIMARY KEY,
        user_id    TEXT,  -- a personal service
        team_id    TEXT REFERENCES teams (id),  -- or a service of a team
        short_name TEXT NOT NULL COLLATE NOCASE,
        name       TEXT NOT NULL DEFAULT '',
        CHECK ((user_id IS NULL) != (team_id IS NULL)),
        UNIQUE (user_id, short_name),
        UNIQUE (team_id, short_name)
    )''',
    'tickets': '''(
        user_id    TEXT NOT NULL,
        key        TEXT NOT NULL,
        service_id TEXT REFERENCES services (id) ON DELETE SET NULL,
        PRIMARY KEY (user_id, key)
    )''',
    'entries': '''(
        id               TEXT NOT NULL PRIMARY KEY,  -- UUIDv7: never reused, so history outlives entries
        user_id          TEXT    NOT NULL,
        date             TEXT    NOT NULL,
        kind             TEXT    NOT NULL CHECK (kind IN ('ticket', 'activity')),
        ticket_key       TEXT,
        activity_type_id TEXT    REFERENCES activity_types (id),
        duration         INTEGER NOT NULL,
        text             TEXT    NOT NULL DEFAULT '',
        coding           INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (user_id, ticket_key) REFERENCES tickets (user_id, key) ON UPDATE CASCADE,
        CHECK (
            (kind = 'ticket' AND activity_type_id IS NULL)
            OR (kind = 'activity' AND activity_type_id IS NOT NULL AND ticket_key IS NULL)
        )
    )''',
    'entry_history': '''(
        id         TEXT NOT NULL PRIMARY KEY,
        user_id    TEXT NOT NULL,
        entry_id   TEXT NOT NULL,  -- no foreign key: the history of deleted entries is kept
        changed_at TEXT NOT NULL,
        action     TEXT NOT NULL,
        changes    TEXT NOT NULL DEFAULT '{}',  -- JSON: {"field": [old, new]}
        detail     TEXT NOT NULL DEFAULT ''     -- e.g. the original spreadsheet line
    )''',
    'review_flags': '''(
        id       TEXT NOT NULL PRIMARY KEY,
        user_id  TEXT NOT NULL,
        entry_id TEXT REFERENCES entries (id) ON DELETE CASCADE,
        date     TEXT,
        reason   TEXT NOT NULL,
        detail   TEXT NOT NULL DEFAULT '',
        CHECK ((entry_id IS NULL) != (date IS NULL))
    )''',
    'work_schedules': '''(
        id                TEXT NOT NULL PRIMARY KEY,
        user_id           TEXT    NOT NULL,
        valid_from        TEXT    NOT NULL,
        weekly_minutes    INTEGER NOT NULL CHECK (weekly_minutes BETWEEN 0 AND 10080),
        work_days         TEXT    NOT NULL,  -- ISO weekdays, e.g. '1,2,3,4,5' for Monday to Friday
        state             TEXT    NOT NULL DEFAULT 'BE',
        company_half_days INTEGER NOT NULL DEFAULT 1 CHECK (company_half_days IN (0, 1)),
        UNIQUE (user_id, valid_from)
    )''',
    'team_memberships': '''(
        id        TEXT NOT NULL PRIMARY KEY,
        team_id   TEXT NOT NULL REFERENCES teams (id),
        user_id   TEXT NOT NULL REFERENCES users (id),
        joined_on TEXT NOT NULL,
        left_on   TEXT,  -- the first day no longer in the team; NULL: still a member
        CHECK (left_on IS NULL OR left_on >= joined_on)
    )''',
    'team_invitations': '''(
        id         TEXT NOT NULL PRIMARY KEY,
        team_id    TEXT NOT NULL REFERENCES teams (id) ON DELETE CASCADE,
        email      TEXT NOT NULL COLLATE NOCASE,  -- no user id: an invitation does not tell whether the user exists
        invited_by TEXT NOT NULL REFERENCES users (id),
        invited_at TEXT NOT NULL,
        UNIQUE (team_id, email)
    )''',
    'report_views': '''(
        id        TEXT NOT NULL PRIMARY KEY,
        member_id TEXT NOT NULL REFERENCES users (id),
        viewer_id TEXT NOT NULL REFERENCES users (id),
        report    TEXT NOT NULL CHECK (report IN ('dashboard', 'week', 'month', 'year')),
        period    TEXT NOT NULL DEFAULT '',  -- e.g. 2026-W44, 2026-10, 2026; empty for the dashboard
        viewed_at TEXT NOT NULL
    )''',
}
_INDEXES = (
    'CREATE INDEX entries_by_user_and_date ON entries (user_id, date)',
    'CREATE INDEX entry_history_by_entry ON entry_history (entry_id)',
    'CREATE INDEX review_flags_by_user ON review_flags (user_id)',
    'CREATE UNIQUE INDEX team_names ON teams (name) WHERE deleted_at IS NULL',
    'CREATE UNIQUE INDEX one_team_per_user ON team_memberships (user_id) WHERE left_on IS NULL',
    'CREATE INDEX team_memberships_by_team ON team_memberships (team_id)',
    'CREATE INDEX report_views_by_member ON report_views (member_id, viewed_at)',
)


def _new_ids(old_ids: Iterable[int]) -> Ids:
    """UUIDv7 ids in the order of the old ones (they are created one after the other, so they sort the same way)."""
    return {old: new_id() for old in sorted(set(old_ids))}


def _ids(conn: sqlite3.Connection, sql: str) -> Ids:
    return _new_ids(row[0] for row in conn.execute(sql))


def to_record_ids(conn: sqlite3.Connection) -> None:
    ids = {table: _ids(conn, f'SELECT id FROM {table}') for table in (
        'activity_types', 'teams', 'services', 'review_flags', 'work_schedules', 'team_memberships', 'team_invitations',
        'report_views', 'entry_history')}
    ids['entries'] = _ids(conn, 'SELECT id FROM entries UNION SELECT entry_id FROM entry_history')
    changed: dict[str, Callable[[sqlite3.Row], tuple]] = {
        'activity_types': lambda row: (ids['activity_types'][row['id']], row['user_id'], row['name']),
        'teams': lambda row: (ids['teams'][row['id']], row['name'], row['deleted_at']),
        'services': lambda row: (ids['services'][row['id']], row['user_id'], _maybe(ids['teams'], row['team_id']),
                                 row['short_name'], row['name']),
        'tickets': lambda row: (row['user_id'], row['key'], _maybe(ids['services'], row['service_id'])),
        'entries': lambda row: (ids['entries'][row['id']], row['user_id'], row['date'], row['kind'], row['ticket_key'],
                                _maybe(ids['activity_types'], row['activity_type_id']), row['duration'], row['text'],
                                row['coding']),
        'entry_history': lambda row: (ids['entry_history'][row['id']], row['user_id'], ids['entries'][row['entry_id']],
                                      row['changed_at'], row['action'], _changes(row['changes'], ids['activity_types']),
                                      _detail(row['detail'], ids['entries'])),
        'review_flags': lambda row: (ids['review_flags'][row['id']], row['user_id'], _maybe(ids['entries'], row['entry_id']),
                                     row['date'], row['reason'], row['detail']),
        'work_schedules': lambda row: (ids['work_schedules'][row['id']], *tuple(row)[1:]),
        'team_memberships': lambda row: (ids['team_memberships'][row['id']], ids['teams'][row['team_id']],
                                         *tuple(row)[2:]),
        'team_invitations': lambda row: (ids['team_invitations'][row['id']], ids['teams'][row['team_id']],
                                         *tuple(row)[2:]),
        'report_views': lambda row: (ids['report_views'][row['id']], *tuple(row)[1:]),
    }
    for table, convert in changed.items():
        _rebuild(conn, table, convert)
    for index in _INDEXES:
        conn.execute(index)


def _rebuild(conn: sqlite3.Connection, table: str, convert: Callable[[sqlite3.Row], tuple]) -> None:
    """The table with text ids: created anew, filled with the converted rows, and put in place of the old one."""
    rows = conn.execute(f'SELECT * FROM {table}').fetchall()
    columns = [description[0] for description in conn.execute(f'SELECT * FROM {table} LIMIT 0').description]
    conn.execute(f'CREATE TABLE new_{table} {_SCHEMA[table]}')
    conn.executemany(f'INSERT INTO new_{table} ({", ".join(columns)}) VALUES ({", ".join("?" for _ in columns)})',
                     [convert(row) for row in rows])
    conn.execute(f'DROP TABLE {table}')
    conn.execute(f'ALTER TABLE new_{table} RENAME TO {table}')


def _maybe(ids: Ids, old: int | None) -> str | None:
    """The new id of a reference that may be empty (or point to a record that is gone)."""
    return ids.get(old) if old is not None else None


def _changes(changes: str, activity_types: Ids) -> str:
    """Activity types named in a history line by their new ids (None for one that no longer exists)."""
    values = json.loads(changes)
    if 'activity_type_id' in values:
        values['activity_type_id'] = [_maybe(activity_types, old) for old in values['activity_type_id']]
    return json.dumps(values)


def _detail(detail: str, entries: Ids) -> str:
    """'Split from entry 4711' with the new id of that entry."""
    match = _SPLIT_FROM.fullmatch(detail)
    return f'Split from entry {entries[int(match[1])]}' if match and int(match[1]) in entries else detail
