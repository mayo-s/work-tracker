import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.database import Database
from src.modules.storage.users import UserRepository
from src.tests.users import KLARA, PASSWORD, USER

# The original setup's services and PTO years, which a new database no longer brings along (migration 6), for the
# first user, who takes over the new database's seeds (activity types, settings, work schedule)
ORIGINAL_SETUP = f"""
    INSERT INTO services (user_id, short_name, name) VALUES
        ('{USER}', 'O365', 'office-integration-service'),
        ('{USER}', 'MSB', 'microsoft-bookings-service'),
        ('{USER}', 'ImmoDrop', ''),
        ('{USER}', 'HiS', 'history-service'),
        ('{USER}', 'TTS', 'text-transformation-service');
    INSERT INTO pto_years (user_id, year, allowance)
        VALUES ('{USER}', 2024, '17.5'), ('{USER}', 2025, '31'), ('{USER}', 2026, '31'), ('{USER}', 2027, '30');
    UPDATE user_settings SET value = '1' WHERE user_id = '{USER}' AND key = 'setup_done';
"""


@pytest.fixture(autouse=True)
def fast_password_hashes(monkeypatch):
    """Cheap scrypt parameters, so creating users does not slow the tests down (test_passwords keeps the real ones)."""
    monkeypatch.setattr('src.lib.passwords._N', 2 ** 4)


@pytest.fixture(autouse=True)
def login_off(monkeypatch):
    """Most tests are about other things: the login is off unless a test switches it on (create_app(auth=True))."""
    monkeypatch.setenv('WORK_TRACKER_AUTH', 'off')


@pytest.fixture
def fresh_database(tmp_path):
    """A new migrated database, not set up yet."""
    db = Database(tmp_path / 'fresh.db')
    db.migrate()
    return db


@pytest.fixture
def database(tmp_path):
    """A migrated database set up for its first user, Klara (id USER), with the original setup's services and PTO years."""
    db = Database(tmp_path / 'work_tracker.db')
    db.migrate()
    with db.transaction() as conn:
        UserRepository(conn, new_id=lambda: USER).add(KLARA, PASSWORD)
    with db.transaction() as conn:
        conn.executescript(ORIGINAL_SETUP)
    return db


@pytest.fixture
def conn(database):
    """A connection within an open transaction on the set-up database."""
    with database.transaction() as connection:
        yield connection


@pytest.fixture
def client(database):
    """A test client for the app on the set-up database."""
    return testing.TestClient(create_app(database))
