"""Review flags in a user's partition (`FLAG#<id>`), each on a day (`date`) or on an entry (`entry_id`)."""

from collections.abc import Callable

from src.models.base import new_id
from src.models.review import ReviewFlag
from src.modules.storage.dynamodb.table import attributes
from src.modules.storage.dynamodb.unit import Unit

FLAG = 'FLAG#'


def flag_key(flag_id: str) -> str:
    return f'{FLAG}{flag_id}'  # a UUIDv7: the flags come in the order they were added


def add_flag(unit: Unit, pk: str, flag: ReviewFlag) -> ReviewFlag:
    added = flag.model_copy(update={'id': new_id()})
    unit.put({'PK': pk, 'SK': flag_key(added.id), **added.model_dump(mode='json')})
    return added


def all_flags(unit: Unit, pk: str) -> list[ReviewFlag]:
    """The user's flags in the order they were added."""
    return [ReviewFlag(**attributes(item)) for item in unit.query_prefix(pk, FLAG)]


def delete_flags(unit: Unit, pk: str, which: Callable[[ReviewFlag], bool]) -> None:
    for flag in all_flags(unit, pk):
        if which(flag):
            unit.delete(pk, flag_key(flag.id))
