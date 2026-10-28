"""Managed lists: services and activity types."""

import sqlite3

from src.models.base import DomainModel
from src.models.catalog import ActivityType, Service
from src.modules.storage.errors import ConflictError, NotFoundError


class _CatalogRepository[M: DomainModel]:
    """List, get, add, update and delete rows of a managed list; works within the given connection's transaction."""

    model: type[M]
    label: str
    table: str
    fields: tuple[str, ...]
    order: str

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def _columns(self) -> str:
        return ', '.join(self.fields)

    def all(self) -> list[M]:
        rows = self._conn.execute(f'SELECT id, {self._columns} FROM {self.table} ORDER BY {self.order}')
        return [self.model(**dict(row)) for row in rows]

    def get(self, item_id: int) -> M:
        row = self._conn.execute(f'SELECT id, {self._columns} FROM {self.table} WHERE id = ?', (item_id,)).fetchone()
        if row is None:
            raise NotFoundError(f'No {self.label} with id {item_id}')
        return self.model(**dict(row))

    def add(self, item: M) -> M:
        placeholders = ', '.join('?' for _ in self.fields)
        cursor = self._write(f'INSERT INTO {self.table} ({self._columns}) VALUES ({placeholders})', self._values(item))
        return item.model_copy(update={'id': cursor.lastrowid})

    def update(self, item: M) -> M:
        assignments = ', '.join(f'{field} = ?' for field in self.fields)
        cursor = self._write(f'UPDATE {self.table} SET {assignments} WHERE id = ?', (*self._values(item), item.id))
        if not cursor.rowcount:
            raise NotFoundError(f'No {self.label} with id {item.id}')
        return item

    def delete(self, item_id: int) -> None:
        if not self._write(f'DELETE FROM {self.table} WHERE id = ?', (item_id,)).rowcount:
            raise NotFoundError(f'No {self.label} with id {item_id}')

    def _values(self, item: M) -> tuple:
        return tuple(getattr(item, field) for field in self.fields)

    def _write(self, sql: str, params: tuple) -> sqlite3.Cursor:
        try:
            return self._conn.execute(sql, params)
        except sqlite3.IntegrityError as error:
            raise ConflictError(f'Cannot change {self.label}: {error}') from error


class ServiceRepository(_CatalogRepository[Service]):
    """Deleting a service unassigns its tickets."""

    model = Service
    label = 'service'
    table = 'services'
    fields = ('short_name', 'name')
    order = 'short_name COLLATE NOCASE'


class ActivityTypeRepository(_CatalogRepository[ActivityType]):
    """An activity type used by entries cannot be deleted."""

    model = ActivityType
    label = 'activity type'
    table = 'activity_types'
    fields = ('name',)
    order = 'id'
