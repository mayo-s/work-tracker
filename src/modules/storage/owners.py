"""Owners of the data: what a new user starts with, and the first user taking over records without an owner."""

import sqlite3

# The nil UUID: the owner of e.g. a new database's seeds, or of data from before users existed, until the first user is created
NO_OWNER = '00000000-0000-0000-0000-000000000000'
PERSONAL_TABLES = ('user_settings', 'services', 'activity_types', 'tickets', 'days', 'entries', 'entry_history',
                   'review_flags', 'pto_years', 'work_schedules')
DEFAULT_ACTIVITY_TYPES = ('Tool Management', 'Meeting', 'Travel', 'Other')


def take_over_unowned(conn: sqlite3.Connection, user_id: str) -> None:
    """All records without an owner become the user's (only for the first user)."""
    for table in PERSONAL_TABLES:
        conn.execute(f'UPDATE {table} SET user_id = ? WHERE user_id = ?', (user_id, NO_OWNER))


def start_with_defaults(conn: sqlite3.Connection, user_id: str) -> None:
    """A user without activity types gets the defaults; without settings, the setup is still to do."""
    if not conn.execute('SELECT 1 FROM activity_types WHERE user_id = ?', (user_id,)).fetchone():
        conn.executemany('INSERT INTO activity_types (user_id, name) VALUES (?, ?)',
                         [(user_id, name) for name in DEFAULT_ACTIVITY_TYPES])
    conn.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?, 'setup_done', '0') "
                 'ON CONFLICT (user_id, key) DO NOTHING', (user_id,))
