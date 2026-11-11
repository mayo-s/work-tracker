"""The audit log on DynamoDB, with the rules of the SQLite repository (audit.py): each entry in the `AUDIT` partition
(`AT#<time>#<id>`), and one about a user also in their partition (`AUDIT#<time>#<id>`), for their own view."""

from src.models.audit import AuditEntry
from src.models.base import new_id
from src.models.users import DELETED_USER
from src.modules.storage.dynamodb.keys import USERS, user_partition
from src.modules.storage.dynamodb.memberships import team_item
from src.modules.storage.dynamodb.table import Item, attributes
from src.modules.storage.dynamodb.unit import Unit

AUDIT = 'AUDIT'
_NAMES = {'actor_name', 'user_name', 'team_name'}


class DynamoAuditLog:
    """Who changed what of whom and when; root and admins read it all, every user the entries about them."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit

    def add(self, entry: AuditEntry) -> None:
        moment = f'{entry.at:%Y-%m-%dT%H:%M:%S.%f}#{new_id()}'  # in time order
        values = entry.model_dump(mode='json', exclude=_NAMES)
        self._unit.put({'PK': AUDIT, 'SK': f'AT#{moment}', **values})
        if entry.user_id:
            self._unit.put({'PK': user_partition(entry.user_id), 'SK': f'AUDIT#{moment}', **values})

    def latest(self, limit: int = 200) -> list[AuditEntry]:
        """The latest entries, newest first."""
        return [self._entry(item) for item in self._unit.newest(AUDIT, 'AT#', limit)]

    def of_user(self, user_id: str, limit: int = 50) -> list[AuditEntry]:
        """The latest entries about the user's account, newest first."""
        return [self._entry(item) for item in self._unit.newest(user_partition(user_id), 'AUDIT#', limit)]

    def all(self) -> list[AuditEntry]:
        """All entries, oldest first (for the full backup)."""
        return [self._entry(item) for item in self._unit.query_prefix(AUDIT, 'AT#')]

    def _entry(self, item: Item) -> AuditEntry:
        team = team_item(self._unit, item['team_id']) if item['team_id'] else None
        return AuditEntry(**attributes(item), actor_name=self._name(item['actor_id']) or DELETED_USER,
                          user_name=self._name(item['user_id']), team_name=team['name'] if team else '')

    def _name(self, user_id: str | None) -> str:
        """The user's name; empty without a user or for a deleted account."""
        profile = self._unit.get(USERS, f'USER#{user_id}') if user_id else None
        return f'{profile["first_name"]} {profile["last_name"]}'.strip() if profile else ''
