"""The DynamoDB backend of the storage interfaces (store.py), used on AWS Lambda; so far users, sessions, login attempts,
settings, days and entries, the other repositories follow."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from src.models.settings import Settings
from src.modules.storage.dynamodb import settings as stored_settings
from src.modules.storage.dynamodb.days import DynamoDays
from src.modules.storage.dynamodb.entries import DynamoEntries
from src.modules.storage.dynamodb.keys import META, SCHEMA
from src.modules.storage.dynamodb.table import Table
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.dynamodb.users import DynamoAttempts, DynamoSessions, DynamoUsers
from src.modules.storage.errors import SchemaVersionError
from src.modules.storage.store import Clock, Theme

# Changes of the item layout, applied once in order: MIGRATIONS[0] brings a table from version 1 to 2, and so on
MIGRATIONS: list[Callable[[Table], None]] = []
LATEST = 1 + len(MIGRATIONS)


class DynamoStore:
    """The repositories and settings within one transaction on the table."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit

    def days(self, user_id: str) -> DynamoDays:
        return DynamoDays(self._unit, user_id)

    def entries(self, user_id: str, clock: Clock | None = None) -> DynamoEntries:
        return DynamoEntries(self._unit, user_id, clock)

    def users(self, clock: Clock | None = None) -> DynamoUsers:
        return DynamoUsers(self._unit, clock)

    def sessions(self) -> DynamoSessions:
        return DynamoSessions(self._unit)

    def attempts(self) -> DynamoAttempts:
        return DynamoAttempts(self._unit)

    def load_settings(self, user_id: str) -> Settings:
        return stored_settings.load_settings(self._unit, user_id)

    def save_settings(self, user_id: str, settings: Settings) -> None:
        stored_settings.save_settings(self._unit, user_id, settings)

    def setup_done(self, user_id: str) -> bool:
        return stored_settings.setup_done(self._unit, user_id)

    def finish_setup(self, user_id: str) -> None:
        stored_settings.finish_setup(self._unit, user_id)

    def load_theme(self, user_id: str) -> Theme:
        return stored_settings.load_theme(self._unit, user_id)

    def save_theme(self, user_id: str, theme: Theme) -> None:
        stored_settings.save_theme(self._unit, user_id, theme)

    def registration_open(self) -> bool:
        return stored_settings.registration_open(self._unit)

    def set_registration(self, enabled: bool) -> None:
        stored_settings.set_registration(self._unit, enabled)


class DynamoStorage:
    """The table as storage backend."""

    def __init__(self, table: Table) -> None:
        self.table = table

    @contextmanager
    def transaction(self) -> Iterator[DynamoStore]:
        """Commit when the block succeeds (at most 100 items at once), write nothing when it raises."""
        unit = Unit(self.table)
        yield DynamoStore(unit)
        unit.flush()

    def migrate(self) -> int:
        """Apply pending migrations; a new table starts at the latest version. Refuses a table of a newer app."""
        item = self.table.get(META, SCHEMA)
        version = int(item['version']) if item else LATEST
        if version > LATEST:
            raise SchemaVersionError(f'Table schema {version} is newer than this app ({LATEST})')
        for number in range(version, LATEST):
            MIGRATIONS[number - 1](self.table)
            self._save_version(number + 1)
        if item is None:
            self._save_version(LATEST)
        return LATEST

    def _save_version(self, version: int) -> None:
        unit = Unit(self.table)
        unit.put({'PK': META, 'SK': SCHEMA, 'version': version})
        unit.flush()
