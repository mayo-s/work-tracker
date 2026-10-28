import sqlite3

import pytest

from src.modules.storage import migrations
from src.modules.storage.database import Database, SchemaVersionError

TABLES = {
    'settings', 'pto_allowances', 'services', 'activity_types', 'tickets', 'days', 'entries', 'entry_history', 'review_flags',
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


def test_migrate_twice_keeps_data_once(database):
    database.migrate()
    with database.transaction() as conn:
        assert conn.execute('SELECT COUNT(*) FROM services').fetchone()[0] == 5


def test_seeded_services(database):
    with database.transaction() as conn:
        services = [tuple(row) for row in conn.execute('SELECT short_name, name FROM services ORDER BY id')]
    assert services == [
        ('O365', 'office-integration-service'),
        ('MSB', 'microsoft-bookings-service'),
        ('ImmoDrop', ''),
        ('HiS', 'history-service'),
        ('TTS', 'text-transformation-service'),
    ]


def test_seeded_activity_types(database):
    with database.transaction() as conn:
        names = [row['name'] for row in conn.execute('SELECT name FROM activity_types ORDER BY id')]
    assert names == ['Tool Management', 'Meeting', 'Travel', 'Other']


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
        conn.execute("INSERT INTO activity_types (name) VALUES ('Incident')")
    with database.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM activity_types WHERE name = 'Incident'").fetchone()[0] == 1


def insert_then_fail(db):
    with db.transaction() as conn:
        conn.execute("INSERT INTO activity_types (name) VALUES ('Incident')")
        raise RuntimeError('abort')


def test_transaction_rolls_back_on_error(database):
    with pytest.raises(RuntimeError):
        insert_then_fail(database)
    with database.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM activity_types WHERE name = 'Incident'").fetchone()[0] == 0


@pytest.mark.parametrize('statement', [
    "INSERT INTO tickets (key, service_id) VALUES ('TNG-1', 99)",
    "INSERT INTO entries (date, kind, ticket_key, duration) VALUES ('2026-10-26', 'ticket', 'TNG-404', 60)",
    "INSERT INTO entries (date, kind, duration) VALUES ('2026-10-26', 'activity', 60)",
    "INSERT INTO entries (date, kind, activity_type_id, duration) VALUES ('2026-10-26', 'meeting', 1, 60)",
    "INSERT INTO review_flags (reason) VALUES ('weekend_hours')",
    "INSERT INTO services (short_name) VALUES ('msb')",
])
def test_constraints(database, statement):
    with database.transaction() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(statement)


def test_deleting_service_unassigns_tickets(database):
    with database.transaction() as conn:
        conn.execute("INSERT INTO services (short_name) VALUES ('AUTH')")
        service_id = conn.execute("SELECT id FROM services WHERE short_name = 'AUTH'").fetchone()[0]
        conn.execute("INSERT INTO tickets (key, service_id) VALUES ('AGA-39', ?)", (service_id,))
        conn.execute("DELETE FROM services WHERE short_name = 'AUTH'")
        assert conn.execute("SELECT service_id FROM tickets WHERE key = 'AGA-39'").fetchone()[0] is None


def test_deleted_entry_ids_are_not_reused(database):
    insert = "INSERT INTO entries (date, kind, activity_type_id, duration) VALUES ('2026-10-26', 'activity', 1, 60)"
    with database.transaction() as conn:
        deleted_id = conn.execute(insert).lastrowid
        conn.execute('DELETE FROM entries WHERE id = ?', (deleted_id,))
        assert conn.execute(insert).lastrowid > deleted_id


def test_entry_history_outlives_deleted_entry(database):
    with database.transaction() as conn:
        entry_id = conn.execute(
            "INSERT INTO entries (date, kind, activity_type_id, duration) VALUES ('2026-10-26', 'activity', 1, 60)"
        ).lastrowid
        conn.execute(
            "INSERT INTO entry_history (entry_id, changed_at, action) VALUES (?, '2026-10-27T14:05:00', 'deleted')",
            (entry_id,),
        )
        conn.execute('DELETE FROM entries WHERE id = ?', (entry_id,))
        assert conn.execute('SELECT COUNT(*) FROM entry_history WHERE entry_id = ?', (entry_id,)).fetchone()[0] == 1


def test_renaming_ticket_updates_entries(database):
    with database.transaction() as conn:
        conn.execute("INSERT INTO tickets (key) VALUES ('TNG-4138')")
        conn.execute(
            "INSERT INTO entries (date, kind, ticket_key, duration) VALUES ('2024-06-10', 'ticket', 'TNG-4138', 360)"
        )
        conn.execute("UPDATE tickets SET key = 'KP-4138' WHERE key = 'TNG-4138'")
        assert conn.execute('SELECT ticket_key FROM entries').fetchone()[0] == 'KP-4138'
