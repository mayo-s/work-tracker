"""Migration to version 2 (TASKS.md 13.7, SPEC 4.6 and 7.2): entries of one kind, an activity optionally on a ticket.

Rewrites every entry item in place (keys and history lines stay), in atomic chunks: an entry, with the activity type
its user gets if they do not have it (Coding, Meeting). An item already converted (no `kind`) is skipped, and the new
version is saved after the last chunk, so a run that stops halfway is finished by the next start. Activity types need
no rewrite: one without `ticket_required` does not require a ticket.
"""

from src.models.catalog import new_activity_type
from src.models.former_entries import convert
from src.modules.storage.dynamodb.catalog import ACTIVITY_TYPE, DynamoActivityTypes
from src.modules.storage.dynamodb.keys import USERS, user_partition
from src.modules.storage.dynamodb.table import Table
from src.modules.storage.dynamodb.unit import Unit

_ITEMS_PER_ENTRY = 3  # the entry, and an activity type with its name item


def to_one_kind(table: Table) -> None:
    unit = Unit(table)
    for profile in unit.query_prefix(USERS, 'USER#'):
        _convert_user(unit, profile['SK'].removeprefix('USER#'))
    unit.flush()


def _convert_user(unit: Unit, user_id: str) -> None:
    pk = user_partition(user_id)
    type_ids = {item['name'].casefold(): item['id'] for item in unit.query_prefix(pk, ACTIVITY_TYPE)}

    def type_id(name: str) -> str:
        if name.casefold() not in type_ids:
            type_ids[name.casefold()] = DynamoActivityTypes(unit, user_id).add(new_activity_type(name)).id
        return type_ids[name.casefold()]

    for item in unit.query_prefix(pk, 'ENTRY#'):
        if 'kind' in item:
            unit.make_room(_ITEMS_PER_ENTRY)
            unit.put(convert(item, type_id))
