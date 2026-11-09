"""The messages of the contact page and their changes on DynamoDB, with the rules of the SQLite repository
(messages.py): each message in the `MESSAGES` partition (`MESSAGE#<id>`), its changes in a partition of its own
(`MESSAGE#<id>`, `CHANGE#<id>`)."""

from src.models.base import new_id
from src.models.messages import SUPPORT, ContactMessage, MessageChange
from src.modules.storage.dynamodb.keys import USERS
from src.modules.storage.dynamodb.table import Item, attributes
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.errors import NotFoundError

MESSAGES = 'MESSAGES'


def message_partition(message_id: str) -> str:
    """The partition of a message's changes."""
    return f'MESSAGE#{message_id}'


class DynamoMessages:
    """Messages newest first, each with its changes (status, notes) oldest first; for support."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit

    def add(self, message: ContactMessage) -> ContactMessage:
        added = message.model_copy(update={'id': new_id()})
        self.restore(added)
        return added

    def get(self, message_id: str) -> ContactMessage:
        item = self._unit.get(MESSAGES, f'MESSAGE#{message_id}')
        if item is None:
            raise NotFoundError(f'No message with id {message_id}')
        return ContactMessage(**attributes(item))

    def all(self) -> list[ContactMessage]:
        """All messages, newest first."""
        messages = [ContactMessage(**attributes(item)) for item in self._unit.query_prefix(MESSAGES, 'MESSAGE#')]
        return sorted(messages, key=lambda message: (message.sent_at, message.id), reverse=True)

    def save(self, message: ContactMessage) -> ContactMessage:
        """Its status, when it was last marked Done, and the sender (anonymized)."""
        self.get(message.id)  # 404 for an unknown one
        self.restore(message)
        return message

    def delete(self, message_id: str) -> None:
        """The message with its changes."""
        self.get(message_id)
        for item in self._unit.query_prefix(message_partition(message_id), 'CHANGE#'):
            self._unit.make_room(1)
            self._unit.delete(item['PK'], item['SK'])
        self._unit.delete(MESSAGES, f'MESSAGE#{message_id}')

    def add_change(self, change: MessageChange) -> MessageChange:
        self.get(change.message_id)  # 404 for an unknown message
        added = change.model_copy(update={'id': new_id()})
        self.restore_change(added)
        return self._named(added.model_dump(exclude={'actor_name'}))

    def changes(self, message_id: str) -> list[MessageChange]:
        """The message's changes, oldest first, with the names of who made them ("Support" once anonymized)."""
        items = self._unit.query_prefix(message_partition(message_id), 'CHANGE#')
        return sorted((self._named(attributes(item)) for item in items), key=lambda change: (change.at, change.id))

    def all_changes(self) -> list[MessageChange]:
        """All changes of all messages, oldest first (for the search and the full backup)."""
        changes = [change for message in self.all() for change in self.changes(message.id)]
        return sorted(changes, key=lambda change: (change.at, change.id))

    def anonymize(self, message_id: str, name: str) -> ContactMessage:
        """The sender becomes `name` (a color and an animal) without e-mail address or account, and who made its
        changes becomes "Support"; subject, text and notes stay."""
        message = self.get(message_id)
        for change in self.changes(message_id):
            self._unit.make_room(1)
            self.restore_change(change.model_copy(update={'actor_id': None}))
        return self.save(message.model_copy(update={'name': name, 'email': '', 'user_id': None, 'anonymized': True}))

    def restore(self, message: ContactMessage) -> None:
        """A message as it was, with its id (also for the full backup)."""
        self._unit.put({'PK': MESSAGES, 'SK': f'MESSAGE#{message.id}', **message.model_dump(mode='json')})

    def restore_change(self, change: MessageChange) -> None:
        """A change as it was, with its id (also for the full backup)."""
        self._unit.put({'PK': message_partition(change.message_id), 'SK': f'CHANGE#{change.id}',
                        **change.model_dump(mode='json', exclude={'actor_name'})})

    def _named(self, values: Item) -> MessageChange:
        profile = self._unit.get(USERS, f'USER#{values["actor_id"]}') if values.get('actor_id') else None
        name = f'{profile["first_name"]} {profile["last_name"]}'.strip() if profile else SUPPORT
        return MessageChange(**values, actor_name=name)
