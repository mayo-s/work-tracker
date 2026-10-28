import pytest

from src.modules.storage.database import Database


@pytest.fixture
def database(tmp_path):
    """A migrated database in a temporary file."""
    db = Database(tmp_path / 'work_tracker.db')
    db.migrate()
    return db


@pytest.fixture
def conn(database):
    """A connection within an open transaction on the migrated database."""
    with database.transaction() as connection:
        yield connection
