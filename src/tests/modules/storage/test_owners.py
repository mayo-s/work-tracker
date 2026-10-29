import datetime as dt
import uuid

import pytest

from src.modules.storage import migrations
from src.modules.storage.catalog import ActivityTypeRepository, ServiceRepository
from src.modules.storage.database import Database
from src.modules.storage.days import DayRepository
from src.modules.storage.owners import NO_OWNER
from src.modules.storage.settings import setup_done
from src.modules.storage.users import UserRepository
from src.tests.users import HANS, PASSWORD, USER


def names(conn, user_id):
    return [activity.name for activity in ActivityTypeRepository(conn, user_id).all()]


def test_first_user_takes_over_the_records_without_owner(fresh_database):
    with fresh_database.transaction() as conn:
        assert names(conn, NO_OWNER) == ['Tool Management', 'Meeting', 'Travel', 'Other']
        user = UserRepository(conn).add(HANS, PASSWORD)
        assert (user.role, names(conn, NO_OWNER)) == ('admin', [])
        assert names(conn, user.id) == ['Tool Management', 'Meeting', 'Travel', 'Other']


def test_another_user_starts_with_defaults_and_the_setup_to_do(conn):
    hans = UserRepository(conn).add(HANS, PASSWORD)
    assert (hans.role, names(conn, hans.id)) == ('user', ['Tool Management', 'Meeting', 'Travel', 'Other'])
    assert (ServiceRepository(conn, hans.id).all(), setup_done(conn, hans.id)) == ([], False)
    assert len(ServiceRepository(conn, USER).all()) == 5  # the first user's stay theirs


@pytest.fixture
def before_users(tmp_path, monkeypatch):
    """A database at schema 7 with a user, a session, a day and entries, one of them deleted (the id must not come
    back); then migrated to the current schema."""
    db = Database(tmp_path / 'seven.db')
    monkeypatch.setattr(migrations, 'MIGRATIONS', migrations.MIGRATIONS[:7])
    db.migrate()
    with db.transaction() as conn:
        conn.execute("INSERT INTO users (username, email, first_name, password_hash)"
                     " VALUES ('klara', 'klara.himmel@example.com', 'Klara', 'x')")
        conn.execute("INSERT INTO sessions VALUES ('hash', 1, '2026-10-30T08:00:00', '2026-10-29T08:00:00')")
        conn.execute("INSERT INTO days (date, day_type) VALUES ('2026-10-28', 'pto')")
        conn.execute("INSERT INTO tickets (key) VALUES ('TNG-1')")
        for _ in range(3):
            conn.execute("INSERT INTO entries (date, kind, ticket_key, duration) VALUES ('2026-10-28', 'ticket', 'TNG-1', 60)")
        conn.execute('DELETE FROM entries WHERE id = 3')
    monkeypatch.undo()
    db.migrate()
    return db


def test_migrations_give_everything_to_the_only_user_who_becomes_admin(before_users):
    with before_users.transaction() as conn:
        user_id, role = conn.execute('SELECT id, role FROM users').fetchone()
        assert (uuid.UUID(user_id).version, role) == (4, 'admin')
        assert DayRepository(conn, user_id).get(dt.date(2026, 10, 28)).day_type == 'pto'
        owners = {table: {row[0] for row in conn.execute(f'SELECT DISTINCT user_id FROM {table}')}
                  for table in ('sessions', 'tickets', 'entries', 'entry_history', 'user_settings', 'activity_types')}
    assert owners == {table: {user_id} for table in owners} | {'entry_history': set()}


def test_migrations_keep_deleted_entry_ids_unused(before_users):
    with before_users.transaction() as conn:
        user_id = conn.execute('SELECT id FROM users').fetchone()[0]
        new_id = conn.execute("INSERT INTO entries (user_id, date, kind, ticket_key, duration) "
                              "VALUES (?, '2026-10-29', 'ticket', 'TNG-1', 60)", (user_id,)).lastrowid
    assert new_id == 4


def test_migrations_without_users_leave_the_records_without_owner(tmp_path, monkeypatch):
    db = Database(tmp_path / 'seven.db')
    monkeypatch.setattr(migrations, 'MIGRATIONS', migrations.MIGRATIONS[:7])
    db.migrate()
    with db.transaction() as conn:
        conn.execute("INSERT INTO days (date, day_type) VALUES ('2026-10-28', 'pto')")
    monkeypatch.undo()
    db.migrate()
    with db.transaction() as conn:
        assert DayRepository(conn, NO_OWNER).get(dt.date(2026, 10, 28)).day_type == 'pto'
