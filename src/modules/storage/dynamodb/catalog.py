"""Managed lists, as the SQLite repositories (catalog.py): services (`SERVICE#<id>`) of a user or a team (in its
partition) and activity types (`ACTIVITY_TYPE#<id>`) of a user. Names are unique per owner, ignoring case, by
`SERVICE_NAME#<lower case>` and `ACTIVITY_TYPE_NAME#<lower case>` items."""

from src.models.base import new_id
from src.models.base import DomainModel
from src.models.catalog import ActivityType, Service, ServiceChoice
from src.modules.storage.dynamodb.keys import user_partition
from src.modules.storage.dynamodb.memberships import current_membership, team_item, team_partition
from src.modules.storage.dynamodb.table import Item, attributes
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.owners import DEFAULT_ACTIVITY_TYPES

ACTIVITY_TYPE, SERVICE = 'ACTIVITY_TYPE#', 'SERVICE#'


def activity_type_key(activity_type_id: str) -> str:
    return f'{ACTIVITY_TYPE}{activity_type_id}'  # a UUIDv7: the sort key keeps the order of creation


def service_key(service_id: str) -> str:
    return f'{SERVICE}{service_id}'


class _DynamoCatalog[M: DomainModel]:
    """List, get, add, update and delete one owner's records of a managed list."""

    model: type[M]
    label: str
    prefix: str
    name: str  # the field that is unique, ignoring case

    def __init__(self, unit: Unit, pk: str) -> None:
        self._unit = unit
        self._pk = pk

    def all(self) -> list[M]:
        return [self.model(**attributes(item)) for item in self._unit.query_prefix(self._pk, self.prefix)]

    def get(self, item_id: str) -> M:
        return self.model(**attributes(self._stored(item_id)))

    def add(self, item: M) -> M:
        added = item.model_copy(update={'id': new_id()})
        self._claim(added)
        self._unit.put({'PK': self._pk, 'SK': self._key(added.id), **added.model_dump()})
        return added

    def update(self, item: M) -> M:
        stored = self._stored(item.id)
        if self._name_key(stored[self.name]) != self._name_key(getattr(item, self.name)):
            self._claim(item)
            self._unit.delete(self._pk, self._name_key(stored[self.name]))
        self._unit.put({'PK': self._pk, 'SK': self._key(item.id), **item.model_dump()})
        return item

    def delete(self, item_id: str) -> None:
        stored = self._stored(item_id)
        self._before_delete(item_id)
        self._unit.delete(self._pk, self._key(item_id))
        self._unit.delete(self._pk, self._name_key(stored[self.name]))

    def _before_delete(self, item_id: str) -> None:
        """What has to happen to records referring to it; nothing by default."""

    def _stored(self, item_id: str) -> Item:
        item = self._unit.get(self._pk, self._key(item_id))
        if item is None:
            raise NotFoundError(f'No {self.label} with id {item_id}')
        return item

    def _claim(self, item: M) -> None:
        value = getattr(item, self.name)
        self._unit.put({'PK': self._pk, 'SK': self._name_key(value), 'id': item.id},
                       unique=f'A {self.label} named "{value}" already exists')

    def _key(self, item_id: str) -> str:
        return f'{self.prefix}{item_id}'

    def _name_key(self, value: str) -> str:
        return f'{self.prefix.rstrip("#")}_NAME#{value.strip().lower()}'


class DynamoServices(_DynamoCatalog[Service]):
    """A user's personal services, sorted by short name; deleting a service unassigns its tickets."""

    model, label, prefix, name = Service, 'service', SERVICE, 'short_name'

    def __init__(self, unit: Unit, user_id: str) -> None:
        super().__init__(unit, user_partition(user_id))
        self._user = user_id

    def all(self) -> list[Service]:
        return sorted(super().all(), key=lambda service: service.short_name.lower())

    def by_short_name(self, short_name: str) -> str | None:
        """The id of the service with this short name (ignoring case), if there is one."""
        item = self._unit.get(self._pk, self._name_key(short_name))
        return item['id'] if item else None

    def choices(self) -> list[ServiceChoice]:
        """The services the user can assign: their team's (while in one) and their personal ones."""
        personal = [ServiceChoice(**service.model_dump()) for service in self.all()]
        membership = current_membership(self._unit, self._user)
        if membership is None:
            return personal
        team = team_item(self._unit, membership['team_id'])['name']
        shared = DynamoTeamServices(self._unit, membership['team_id']).all()
        return [ServiceChoice(**service.model_dump(), team=team) for service in shared] + personal

    def _before_delete(self, item_id: str) -> None:
        unassign(self._unit, self._pk, item_id)


class DynamoTeamServices(DynamoServices):
    """A team's services, which its members choose; deleting one unassigns the members' tickets."""

    def __init__(self, unit: Unit, team_id: str) -> None:
        _DynamoCatalog.__init__(self, unit, team_partition(team_id))  # the team's partition: no user of its own

    def _before_delete(self, item_id: str) -> None:
        for member in self._unit.query_prefix(self._pk, 'MEMBER#'):
            unassign(self._unit, user_partition(member['user_id']), item_id)


def unassign(unit: Unit, pk: str, service_id: str) -> None:
    """The service no longer on the tickets of a user's partition (in chunks, before the service itself goes)."""
    for ticket in unit.query_prefix(pk, 'TICKET#'):
        if ticket['service_id'] == service_id:
            unit.make_room(2)  # the ticket now, the service with its name at the end
            unit.put(ticket | {'service_id': None})


class DynamoActivityTypes(_DynamoCatalog[ActivityType]):
    """Activity types in the order they were created; one used by entries cannot be deleted."""

    model, label, prefix, name = ActivityType, 'activity type', ACTIVITY_TYPE, 'name'

    def __init__(self, unit: Unit, user_id: str) -> None:
        super().__init__(unit, user_partition(user_id))

    def _before_delete(self, item_id: str) -> None:
        if any(entry.get('activity_type_id') == item_id for entry in self._unit.query_prefix(self._pk, 'ENTRY#')):
            raise ConflictError(f'The {self.label} is used by entries and cannot be deleted')


def add_default_activity_types(unit: Unit, user_id: str) -> None:
    """A new user starts with the default activity types."""
    activity_types = DynamoActivityTypes(unit, user_id)
    for name in DEFAULT_ACTIVITY_TYPES:
        activity_types.add(ActivityType(name=name))
