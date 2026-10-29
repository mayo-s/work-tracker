import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.database import Database

# The original setup's services and PTO years, which a new database no longer brings along (migration 6)
ORIGINAL_SETUP = """
    INSERT INTO services (short_name, name) VALUES
        ('O365', 'office-integration-service'),
        ('MSB', 'microsoft-bookings-service'),
        ('ImmoDrop', ''),
        ('HiS', 'history-service'),
        ('TTS', 'text-transformation-service');
    INSERT INTO pto_years (year, allowance) VALUES (2024, '17.5'), (2025, '31'), (2026, '31'), (2027, '30');
    UPDATE settings SET value = '1' WHERE key = 'setup_done';
"""


@pytest.fixture
def fresh_database(tmp_path):
    """A new migrated database, not set up yet."""
    db = Database(tmp_path / 'fresh.db')
    db.migrate()
    return db


@pytest.fixture
def database(tmp_path):
    """A migrated, set-up database with the original setup's services and PTO years."""
    db = Database(tmp_path / 'work_tracker.db')
    db.migrate()
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
