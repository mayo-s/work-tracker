"""Where teams and memberships are (keys.py): teams in the `TEAMS` partition, a team's members, invitations and services
in its own partition `TEAM#<id>`, and each user's memberships (`MEMBERSHIP#<id>`, kept as history) in their partition."""

from src.modules.storage.dynamodb.keys import user_partition
from src.modules.storage.dynamodb.table import Item
from src.modules.storage.dynamodb.unit import Unit

TEAMS, MEMBERSHIP = 'TEAMS', 'MEMBERSHIP#'


def team_key(team_id: int) -> str:
    """A team's item in the `TEAMS` partition."""
    return f'TEAM#{team_id:010d}'


def team_partition(team_id: int) -> str:
    """The partition of a team's members, invitations and services."""
    return f'TEAM#{team_id}'


def team_item(unit: Unit, team_id: int) -> Item | None:
    """The team, also a deleted one (it stays for the history)."""
    return unit.get(TEAMS, team_key(team_id))


def current_membership(unit: Unit, user_id: str) -> Item | None:
    """The user's membership in the team they are in now, if any."""
    return next((item for item in unit.query_prefix(user_partition(user_id), MEMBERSHIP) if item['left_on'] is None), None)
