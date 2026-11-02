import sqlite3

import pytest

from src.models.base import new_id
from src.modules.storage import migrations
from src.modules.storage.database import Database, SchemaVersionError
from src.modules.storage.owners import NO_OWNER
from src.tests.users import USER

TABLES = {
    'settings', 'user_settings', 'pto_years', 'work_schedules', 'services', 'activity_types', 'tickets', 'days', 'entries',
    'entry_history', 'review_flags', 'users', 'sessions', 'login_attempts', 'teams', 'team_memberships', 'team_invitations',
    'report_views',
}


def table_names(db):
    query = "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    with db.transaction() as conn:
        return {row['name'] for row in conn.execute(query)}


def test_migrate_new_database(tmp_path):
    db = Database(tmp_path / 'new.db')
    assert db.schema_version() == 0
    assert db.migrate() == len(migrations.MIGRATIONS)
    assert db.schema_version() == len(migrations.MIGRATIONS)
    assert table_names(db) == TABLES


def count(db, table):
    with db.transaction() as conn:
        return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


def test_migrate_twice_keeps_data_once(fresh_database):
    fresh_database.migrate()
    assert count(fresh_database, 'activity_types') == 4


def test_new_database_starts_clean(fresh_database):
    with fresh_database.transaction() as conn:
        names = [row['name'] for row in conn.execute('SELECT name FROM activity_types ORDER BY id')]
        setup_done = conn.execute("SELECT value FROM user_settings WHERE user_id = ? AND key = 'setup_done'",
                                  (NO_OWNER,)).fetchone()[0]
    assert names == ['Tool Management', 'Meeting', 'Travel', 'Other']
    assert (count(fresh_database, 'services'), count(fresh_database, 'pto_years'), setup_done) == (0, 0, '0')


def test_database_in_use_keeps_its_data_and_counts_as_set_up(tmp_path, monkeypatch):
    db = Database(tmp_path / 'in-use.db')
    monkeypatch.setattr(migrations, 'MIGRATIONS', migrations.MIGRATIONS[:5])
    db.migrate()
    with db.transaction() as conn:
        conn.execute("INSERT INTO days (date, day_type) VALUES ('2026-10-28', 'pto')")
    monkeypatch.undo()
    db.migrate()
    with db.transaction() as conn:
        setup_done = conn.execute("SELECT value FROM user_settings WHERE user_id = ? AND key = 'setup_done'",
                                  (NO_OWNER,)).fetchone()[0]
    assert (count(db, 'services'), count(db, 'pto_years'), setup_done) == (5, 4, '1')


def test_a_team_admin_becomes_a_user_who_is_team_admin_of_their_team(tmp_path, monkeypatch):
    db = Database(tmp_path / 'team-admins.db')
    monkeypatch.setattr(migrations, 'MIGRATIONS', migrations.MIGRATIONS[:14])
    db.migrate()
    ids = {name: new_id() for name in ('klara', 'hans', 'rainer', 'team', 'now', 'before')}
    with db.transaction() as conn:
        for name, role in (('klara', 'admin'), ('hans', 'team_admin'), ('rainer', 'user')):
            conn.execute("INSERT INTO users (id, username, email, first_name, password_hash, role) VALUES (?, ?, ?, ?, '', ?)",
                         (ids[name], name, f'{name}@example.com', name.title(), role))
        conn.execute("INSERT INTO teams (id, name) VALUES (?, 'Platform')", (ids['team'],))
        conn.executemany('INSERT INTO team_memberships (id, team_id, user_id, joined_on, left_on) VALUES (?, ?, ?, ?, ?)', [
            (ids['before'], ids['team'], ids['hans'], '2026-01-01', '2026-06-01'),
            (ids['now'], ids['team'], ids['hans'], '2026-06-01', None),
        ])
    monkeypatch.undo()
    db.migrate()
    with db.transaction() as conn:
        roles = [tuple(row) for row in conn.execute('SELECT username, role FROM users ORDER BY rowid')]
        team_roles = [tuple(row) for row in conn.execute(
            'SELECT joined_on, team_role FROM team_memberships ORDER BY joined_on')]
    assert roles == [('klara', 'admin'), ('hans', 'user'), ('rainer', 'user')]
    assert team_roles == [('2026-01-01', 'member'), ('2026-06-01', 'team_admin')]


def test_migrate_rejects_newer_schema(database, monkeypatch):
    monkeypatch.setattr(migrations, 'MIGRATIONS', ())
    with pytest.raises(SchemaVersionError):
        database.migrate()


def test_failed_migration_is_rolled_back(database, monkeypatch):
    broken = 'CREATE TABLE half_done (id INTEGER); INSERT INTO missing_table VALUES (1);'
    monkeypatch.setattr(migrations, 'MIGRATIONS', (*migrations.MIGRATIONS, broken))
    with pytest.raises(sqlite3.OperationalError):
        database.migrate()
    assert database.schema_version() == len(migrations.MIGRATIONS) - 1
    assert 'half_done' not in table_names(database)


def test_transaction_commits(database):
    with database.transaction() as conn:
        conn.execute("INSERT INTO activity_types (id, user_id, name) VALUES (?, ?, 'Incident')", (new_id(), USER))
    with database.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM activity_types WHERE name = 'Incident'").fetchone()[0] == 1


def insert_then_fail(db):
    with db.transaction() as conn:
        conn.execute("INSERT INTO activity_types (id, user_id, name) VALUES (?, ?, 'Incident')", (new_id(), USER))
        raise RuntimeError('abort')


def test_transaction_rolls_back_on_error(database):
    with pytest.raises(RuntimeError):
        insert_then_fail(database)
    with database.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM activity_types WHERE name = 'Incident'").fetchone()[0] == 0


@pytest.mark.parametrize('statement', [
    "INSERT INTO tickets (user_id, key, service_id) VALUES (?, 'TNG-1', 99)",
    "INSERT INTO entries (user_id, date, kind, ticket_key, duration) VALUES (?, '2026-10-26', 'ticket', 'TNG-404', 60)",
    "INSERT INTO entries (user_id, date, kind, duration) VALUES (?, '2026-10-26', 'activity', 60)",
    "INSERT INTO entries (user_id, date, kind, activity_type_id, duration) VALUES (?, '2026-10-26', 'meeting', 1, 60)",
    "INSERT INTO review_flags (user_id, reason) VALUES (?, 'weekend_hours')",
    "INSERT INTO services (user_id, short_name) VALUES (?, 'msb')",
    "INSERT INTO days (user_id) VALUES (?)",
])
def test_constraints(database, statement):
    with database.transaction() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(statement, (USER,))


ROOT = "INSERT INTO users (id, username, email, first_name, password_hash, role) VALUES (?, ?, ?, 'Root', '', 'root')"


def test_one_root_only(database):
    with database.transaction() as conn:
        conn.execute(ROOT, (new_id(), 'rainer', 'rainer.zufall@example.com'))
    with database.transaction() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(ROOT, (new_id(), 'pascal', 'turbo.pascal@example.com'))
