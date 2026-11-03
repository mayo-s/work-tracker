"""Everything but root goes, before a full backup is restored (SPEC 5.9), in atomic chunks: every other user with their
partition, login names and sessions, the teams with their members, invitations, services and auditors, the audit log
and the failed logins. Root (profile, settings, sessions), the app settings, the used setup tokens and the schema
version stay."""

from src.modules.storage.dynamodb.audit import AUDIT
from src.modules.storage.dynamodb.keys import ATTEMPTS, LOGIN, USERS, user_partition
from src.modules.storage.dynamodb.memberships import TEAMS, team_partition
from src.modules.storage.dynamodb.table import Item
from src.modules.storage.dynamodb.unit import Unit

_FIRST, _LAST = ' ', '\U0010ffff'  # sort keys are printable: these bound all of a partition's


def purge(unit: Unit, root_id: str) -> None:
    for profile in unit.query_prefix(USERS, 'USER#'):
        if profile['id'] != root_id:
            _purge_user(unit, profile)
    _delete(unit, unit.query_prefix(user_partition(root_id), 'AUDIT#'))  # root's view of the audit log goes with it
    for team in unit.query_prefix(TEAMS, 'TEAM#'):
        _purge_team(unit, team['id'])
    for pk in (TEAMS, AUDIT, ATTEMPTS):
        _delete(unit, _partition(unit, pk))


def _purge_team(unit: Unit, team_id: str) -> None:
    """The team's members, stays, invitations (also by e-mail address), services and auditors."""
    for item in _partition(unit, team_partition(team_id)):
        if item['SK'].startswith('INVITE#'):
            _delete(unit, [{'PK': f'INVITES#{item["email"].strip().lower()}', 'SK': f'TEAM#{team_id}'}])
        _delete(unit, [item])


def _purge_user(unit: Unit, profile: Item) -> None:
    pk = user_partition(profile['id'])
    _delete(unit, [{'PK': reference['SK'], 'SK': 'SESSION'} for reference in unit.query_prefix(pk, 'SESSION#')])
    _delete(unit, _partition(unit, pk))  # with the references to the sessions
    _delete(unit, [{'PK': LOGIN, 'SK': f'USERNAME#{profile["username"].strip().lower()}'},
                   {'PK': LOGIN, 'SK': f'EMAIL#{profile["email"].strip().lower()}'}, profile])


def _partition(unit: Unit, pk: str) -> list[Item]:
    return unit.query(pk, _FIRST, _LAST)


def _delete(unit: Unit, items: list[Item]) -> None:
    for item in items:
        unit.make_room(1)
        unit.delete(item['PK'], item['SK'])
