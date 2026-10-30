"""The DynamoDB backend of the storage interfaces (store.py), used on AWS Lambda; it holds the app settings so far,
the repositories follow."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from src.modules.storage.dynamodb.keys import APP, META, SCHEMA, SETTINGS
from src.modules.storage.dynamodb.table import Table
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.errors import SchemaVersionError

# Changes of the item layout, applied once in order: MIGRATIONS[0] brings a table from version 1 to 2, and so on
MIGRATIONS: list[Callable[[Table], None]] = []
LATEST = 1 + len(MIGRATIONS)


class DynamoStore:
    """The repositories and settings within one transaction on the table."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit

    def registration_open(self) -> bool:
        """Whether new users can register on /register (off until an admin switches it on)."""
        return bool((self._unit.get(APP, SETTINGS) or {}).get('registration'))

    def set_registration(self, enabled: bool) -> None:
        settings = self._unit.get(APP, SETTINGS) or {'PK': APP, 'SK': SETTINGS}
        self._unit.put(settings | {'registration': enabled})


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
