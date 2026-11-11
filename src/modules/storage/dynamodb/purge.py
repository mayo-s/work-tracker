"""Everything but root goes, before a full backup is restored (SPEC 5.9), in atomic chunks: every other user with their
partition, login names and sessions, the teams with their members, invitations, services and auditors, the audit log,
the failed logins and the messages of the contact page with their changes. Root (profile, settings, sessions), the app
settings, the used setup tokens and the schema version stay.

A deleted account goes the same way, alone (SPEC 5.7, delete_user)."""

from src.modules.storage.dynamodb.audit import AUDIT
from src.modules.storage.dynamodb.keys import ATTEMPTS, LOGIN, USERS, user_partition
from src.modules.storage.dynamodb.memberships import MEMBERSHIP, TEAMS, team_partition
from src.modules.storage.dynamodb.messages import MESSAGES, message_partition
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
    for message in unit.query_prefix(MESSAGES, 'MESSAGE#'):
        _delete(unit, _partition(unit, message_partition(message['id'])))
    for pk in (TEAMS, AUDIT, ATTEMPTS, MESSAGES):
        _delete(unit, _partition(unit, pk))


def delete_user(unit: Unit, user_id: str) -> None:
    """The user goes with everything of theirs, as on SQLite (owners.py), in atomic chunks; the profile and login names
    go last, so deleting again finishes a deletion that stopped halfway. Their messages must be anonymized first."""
    profile = unit.get(USERS, f'USER#{user_id}')
    for invitation in unit.query_prefix(f'INVITES#{profile["email"].strip().lower()}', 'TEAM#'):
        _delete(unit, [{'PK': team_partition(invitation['team_id']), 'SK': f'INVITE#{invitation["id"]}'}, invitation])
    _forget_changes(unit, user_id)
    _delete(unit, [item for item in _partition(unit, AUDIT) if item.get('user_id') == user_id])
    _leave_teams(unit, user_id)
    _purge_user(unit, profile)


def _forget_changes(unit: Unit, user_id: str) -> None:
    """Their status changes and notes on contact messages become "Support"'s."""
    for message in unit.query_prefix(MESSAGES, 'MESSAGE#'):
        for change in unit.query_prefix(message_partition(message['id']), 'CHANGE#'):
            if change.get('actor_id') == user_id:
                unit.make_room(1)
                unit.put(change | {'actor_id': None})


def _leave_teams(unit: Unit, user_id: str) -> None:
    """Their stays in teams, current and former, and their auditor assignments go from the teams' partitions."""
    pk = user_partition(user_id)
    for stay in unit.query_prefix(pk, MEMBERSHIP):
        _delete(unit, [{'PK': team_partition(stay['team_id']), 'SK': f'STAY#{stay["SK"].removeprefix(MEMBERSHIP)}'},
                       {'PK': team_partition(stay['team_id']), 'SK': f'MEMBER#{user_id}'}])
    _delete(unit, [{'PK': team_partition(item['team_id']), 'SK': f'AUDITOR#{user_id}'}
                   for item in unit.query_prefix(pk, 'AUDITS#')])


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
