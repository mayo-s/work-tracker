"""Managed lists in a user's partition: activity types (`ACTIVITY_TYPE#<id>`); so far the defaults of a new user."""

from src.modules.storage.dynamodb.keys import user_partition
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.owners import DEFAULT_ACTIVITY_TYPES

ACTIVITY_TYPE = 'ACTIVITY_TYPE#'


def activity_type_key(activity_type_id: int) -> str:
    return f'{ACTIVITY_TYPE}{activity_type_id:010d}'  # zero-padded, so the sort key keeps the order of creation


def add_default_activity_types(unit: Unit, user_id: str) -> None:
    """A new user starts with the four default activity types."""
    for name in DEFAULT_ACTIVITY_TYPES:
        activity_type_id = unit.next_id('activity_type')
        unit.put({'PK': user_partition(user_id), 'SK': activity_type_key(activity_type_id), 'id': activity_type_id,
                  'name': name})
