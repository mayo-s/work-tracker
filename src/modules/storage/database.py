"""SQLite connection handling and schema migration."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from src.modules.storage import migrations

DEFAULT_PATH = 'work_tracker.db'


def database_path() -> str:
    """The database file: $WORK_TRACKER_DB, or work_tracker.db in the working directory."""
    return os.environ.get('WORK_TRACKER_DB', DEFAULT_PATH)


class SchemaVersionError(RuntimeError):
    """Raised when the database was created by a newer version of the app."""


class Database:
    """A SQLite database file; each transaction uses its own connection."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, autocommit=True)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')  # has no effect inside a transaction, so set it first
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Commit when the block succeeds, roll back when it raises."""
        conn = self._connect()
        conn.autocommit = False
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def schema_version(self) -> int:
        conn = self._connect()
        try:
            return conn.execute('PRAGMA user_version').fetchone()[0]
        finally:
            conn.close()

    def migrate(self) -> int:
        """Apply pending migrations, each in its own transaction; returns the schema version.

        Foreign keys are off while migrating, so a script can rebuild a table (create, copy, drop, rename) without
        its references acting on the drop; they are checked before each commit instead.
        """
        version, latest = self.schema_version(), len(migrations.MIGRATIONS)
        if version > latest:
            raise SchemaVersionError(f'Database schema {version} is newer than this app ({latest})')
        conn = self._connect()
        conn.execute('PRAGMA foreign_keys = OFF')
        try:
            for number in range(version + 1, latest + 1):
                _apply(conn, migrations.MIGRATIONS[number - 1], number)
        finally:
            conn.close()
        return latest


def _apply(conn: sqlite3.Connection, script: str, number: int) -> None:
    """One migration in one transaction; rolled back if it fails or leaves a broken reference."""
    try:
        conn.executescript(f'BEGIN;\n{script}\nPRAGMA user_version = {number};')
        if broken := conn.execute('PRAGMA foreign_key_check').fetchall():
            raise sqlite3.IntegrityError(f'Migration {number} leaves broken references: {[tuple(row) for row in broken]}')
        conn.execute('COMMIT')
    except BaseException:
        if conn.in_transaction:
            conn.execute('ROLLBACK')
        raise
