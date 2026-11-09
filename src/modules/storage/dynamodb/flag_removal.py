"""Migration to version 3 (TASKS.md L.12): the review flags of the former spreadsheet import (`FLAG#<id>` in a user's
partition) go, in atomic chunks; a run that stops halfway is finished by the next start."""

from src.modules.storage.dynamodb.keys import USERS, user_partition
from src.modules.storage.dynamodb.table import Table
from src.modules.storage.dynamodb.unit import Unit


def drop_flags(table: Table) -> None:
    unit = Unit(table)
    for profile in unit.query_prefix(USERS, 'USER#'):
        pk = user_partition(profile['SK'].removeprefix('USER#'))
        for flag in unit.query_prefix(pk, 'FLAG#'):
            unit.make_room(1)
            unit.delete(pk, flag['SK'])
    unit.flush()
