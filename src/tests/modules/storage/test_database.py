import sqlite3

import pytest

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
        conn.execute("INSERT INTO activity_types (user_id, name) VALUES (?, 'Incident')", (USER,))
    with database.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM activity_types WHERE name = 'Incident'").fetchone()[0] == 1


def insert_then_fail(db):
    with db.transaction() as conn:
        conn.execute("INSERT INTO activity_types (user_id, name) VALUES (?, 'Incident')", (USER,))
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


def test_deleted_entry_ids_are_not_reused(database):
    insert = ("INSERT INTO entries (user_id, date, kind, activity_type_id, duration)"
              f" VALUES ('{USER}', '2026-10-26', 'activity', 1, 60)")
    with database.transaction() as conn:
        deleted_id = conn.execute(insert).lastrowid
        conn.execute('DELETE FROM entries WHERE id = ?', (deleted_id,))
        assert conn.execute(insert).lastrowid > deleted_id
