"""Managed lists: services and activity types."""

import sqlite3

from src.models.base import DomainModel
from src.models.catalog import ActivityType, Service, ServiceChoice
from src.modules.storage.errors import ConflictError, NotFoundError


class _CatalogRepository[M: DomainModel]:
    """List, get, add, update and delete one owner's rows of a managed list (a user's, or for team services a team's);
    works within the given connection's transaction."""

    model: type[M]
    label: str
    table: str
    fields: tuple[str, ...]
    order: str
    owner: str = 'user_id'

    def __init__(self, conn: sqlite3.Connection, owner_id: str | int) -> None:
        self._conn = conn
        self._owner = owner_id

    @property
    def _columns(self) -> str:
        return ', '.join(self.fields)

    def all(self) -> list[M]:
        rows = self._conn.execute(f'SELECT id, {self._columns} FROM {self.table} WHERE {self.owner} = ? ORDER BY {self.order}',
                                  (self._owner,))
        return [self.model(**dict(row)) for row in rows]

    def get(self, item_id: int) -> M:
        row = self._conn.execute(f'SELECT id, {self._columns} FROM {self.table} WHERE id = ? AND {self.owner} = ?',
                                 (item_id, self._owner)).fetchone()
        if row is None:
            raise NotFoundError(f'No {self.label} with id {item_id}')
        return self.model(**dict(row))

    def add(self, item: M) -> M:
        placeholders = ', '.join('?' for _ in self.fields)
        sql = f'INSERT INTO {self.table} ({self.owner}, {self._columns}) VALUES (?, {placeholders})'
        cursor = self._write(sql, (self._owner, *self._values(item)), self._duplicate(item))
        return item.model_copy(update={'id': cursor.lastrowid})

    def update(self, item: M) -> M:
        assignments = ', '.join(f'{field} = ?' for field in self.fields)
        sql = f'UPDATE {self.table} SET {assignments} WHERE id = ? AND {self.owner} = ?'
        cursor = self._write(sql, (*self._values(item), item.id, self._owner), self._duplicate(item))
        if not cursor.rowcount:
            raise NotFoundError(f'No {self.label} with id {item.id}')
        return item

    def delete(self, item_id: int) -> None:
        in_use = f'The {self.label} is used by entries and cannot be deleted'
        sql = f'DELETE FROM {self.table} WHERE id = ? AND {self.owner} = ?'
        if not self._write(sql, (item_id, self._owner), in_use).rowcount:
            raise NotFoundError(f'No {self.label} with id {item_id}')

    def _values(self, item: M) -> tuple:
        return tuple(getattr(item, field) for field in self.fields)

    def _duplicate(self, item: M) -> str:
        return f'A {self.label} named "{self._values(item)[0]}" already exists'

    def _write(self, sql: str, params: tuple, conflict: str) -> sqlite3.Cursor:
        """Runs a change; a unique or foreign key violation raises a ConflictError with the given message."""
        try:
            return self._conn.execute(sql, params)
        except sqlite3.IntegrityError as error:
            raise ConflictError(conflict) from error


class ServiceRepository(_CatalogRepository[Service]):
    """A user's personal services; deleting a service unassigns its tickets."""

    model = Service
    label = 'service'
    table = 'services'
    fields = ('short_name', 'name')
    order = 'short_name COLLATE NOCASE'

    def choices(self) -> list[ServiceChoice]:
        """The services the user can assign: their team's (while in one) and their personal ones."""
        rows = self._conn.execute(
            'SELECT services.id, short_name, services.name, teams.name AS team FROM services'
            ' LEFT JOIN teams ON teams.id = services.team_id'
            ' WHERE services.user_id = ? OR services.team_id = (SELECT team_id FROM team_memberships'
            '     WHERE user_id = ? AND left_on IS NULL)'
            ' ORDER BY team IS NULL, short_name COLLATE NOCASE', (self._owner, self._owner))
        return [ServiceChoice(**dict(row)) for row in rows]


class TeamServiceRepository(ServiceRepository):
    """A team's services, which its members choose; only the admin and the team's admins change them."""

    owner = 'team_id'


class ActivityTypeRepository(_CatalogRepository[ActivityType]):
    """An activity type used by entries cannot be deleted."""

    model = ActivityType
    label = 'activity type'
    table = 'activity_types'
    fields = ('name',)
    order = 'id'
