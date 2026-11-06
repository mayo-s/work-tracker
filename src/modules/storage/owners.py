"""Owners of the data: what a new user starts with, the first user taking over records without an owner, and everyone
but root going before a full backup is restored."""

import sqlite3

from src.models.base import new_id

# The nil UUID: the owner of e.g. a new database's seeds, or of data from before users existed, until the first user is created
NO_OWNER = '00000000-0000-0000-0000-000000000000'
PERSONAL_TABLES = ('user_settings', 'services', 'activity_types', 'tickets', 'days', 'entries', 'entry_history',
                   'review_flags', 'pto_years', 'work_schedules')
DEFAULT_ACTIVITY_TYPES = ('Meeting', 'Travel', 'Planning', 'Documentation', 'Other')


def take_over_unowned(conn: sqlite3.Connection, user_id: str) -> None:
    """All records without an owner become the user's (only for the first user who is not root)."""
    for table in PERSONAL_TABLES:
        conn.execute(f'UPDATE {table} SET user_id = ? WHERE user_id = ?', (user_id, NO_OWNER))


def clear_records(conn: sqlite3.Connection, user_id: str) -> None:
    """The user's own records go (days, entries with history and flags, tickets, services, activity types, work
    schedules, PTO years); their account and settings stay."""
    for table in ('review_flags', 'entry_history', 'entries', 'days', 'tickets', 'services', 'activity_types', 'pto_years',
                  'work_schedules'):
        conn.execute(f'DELETE FROM {table} WHERE user_id = ?', (user_id,))


def purge(conn: sqlite3.Connection, root_id: str) -> None:
    """Everything but root goes (SPEC 5.9): every other user with their records, settings, sessions and browsers, the
    teams with their members, invitations, services and auditors, the report view log, the audit log and the failed
    logins. Root (settings, sessions), the records without an owner, the app settings and the used setup tokens stay."""
    for table in ('report_views', 'audit_log', 'team_auditors', 'team_invitations', 'team_memberships'):
        conn.execute(f'DELETE FROM {table}')
    for table in ('review_flags', 'entry_history', 'entries', 'days', 'tickets', 'services', 'activity_types', 'pto_years',
                  'work_schedules', 'user_settings'):  # team services have no user: they go too
        conn.execute(f'DELETE FROM {table} WHERE user_id IS NULL OR user_id NOT IN (?, ?)', (root_id, NO_OWNER))
    conn.execute('DELETE FROM teams')
    conn.execute('DELETE FROM login_attempts')
    conn.execute('DELETE FROM users WHERE id != ?', (root_id,))  # their sessions and browsers with them


def start_with_defaults(conn: sqlite3.Connection, user_id: str) -> None:
    """A user without activity types gets the defaults; without settings, the setup is still to do."""
    if not conn.execute('SELECT 1 FROM activity_types WHERE user_id = ?', (user_id,)).fetchone():
        conn.executemany('INSERT INTO activity_types (id, user_id, name) VALUES (?, ?, ?)',
                         [(new_id(), user_id, name) for name in DEFAULT_ACTIVITY_TYPES])
    conn.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?, 'setup_done', '0') "
                 'ON CONFLICT (user_id, key) DO NOTHING', (user_id,))
