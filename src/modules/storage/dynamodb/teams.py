"""Teams, their members (kept as history), invitations and the log of the team view on DynamoDB, with the rules of
the SQLite repositories (teams.py); where the items are: memberships.py.

Team names are unique among the teams that exist (`TEAMS` / `NAME#<lower case>`). An invitation is kept twice: in the
team's partition (`INVITE#<id>`) and by e-mail address (`INVITES#<lower case>` / `TEAM#<id>`), for the invited user.
A member's report views are in their partition (`VIEW#<time>#<id>`).
"""

import datetime as dt
from collections.abc import Callable

from src.models.base import new_id
from src.models.catalog import Service
from src.models.teams import Auditor, Invitation, Member, Membership, ReportView, Team, TeamRole
from src.modules.storage.dynamodb.catalog import DynamoServices, DynamoTeamServices
from src.modules.storage.dynamodb.keys import USERS, user_partition
from src.modules.storage.dynamodb.memberships import (
    MEMBERSHIP, TEAMS, current_membership, team_item, team_key, team_partition,
)
from src.modules.storage.dynamodb.table import Item, attributes
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.store import Teams


def _membership(unit: Unit, item: Item) -> Membership:
    return Membership(team_id=item['team_id'], team_name=team_item(unit, item['team_id'])['name'], user_id=item['user_id'],
                      joined_on=item['joined_on'], left_on=item['left_on'], team_role=item.get('team_role', 'member'))


def _profile(unit: Unit, user_id: str) -> Item | None:
    return unit.get(USERS, f'USER#{user_id}')


class DynamoTeams:
    """Teams and who is in them. A user is in at most one team; joining another leaves the current one."""

    def __init__(self, unit: Unit, clock: Callable[[], dt.datetime] | None = None) -> None:
        self._unit = unit
        self._clock = clock or dt.datetime.now

    def all(self) -> list[Team]:
        teams = [Team(id=item['id'], name=item['name']) for item in self._unit.query_prefix(TEAMS, 'TEAM#')
                 if item['deleted_at'] is None]
        return sorted(teams, key=lambda team: team.name.lower())

    def get(self, team_id: str) -> Team:
        item = team_item(self._unit, team_id)
        if item is None or item['deleted_at'] is not None:
            raise NotFoundError(f'No team with id {team_id}')
        return Team(id=item['id'], name=item['name'])

    def add(self, team: Team) -> Team:
        added = team.model_copy(update={'id': new_id()})
        self._claim(added.name, added.id)
        self._unit.put({'PK': TEAMS, 'SK': team_key(added.id), 'id': added.id, 'name': added.name, 'deleted_at': None})
        return added

    def rename(self, team: Team) -> Team:
        stored = self.get(team.id)
        if stored.name.lower() != team.name.lower():
            self._claim(team.name, team.id)
            self._unit.delete(TEAMS, _name_key(stored.name))
        self._unit.put(team_item(self._unit, team.id) | {'name': team.name})
        return team

    def delete(self, team_id: str) -> None:
        """Only a team without members; its open invitations, services and auditors go with it, its history stays."""
        stored = self.get(team_id)
        if self.members(team_id):
            raise ConflictError('The team still has members; remove them first')
        for invitation in self._unit.query_prefix(team_partition(team_id), 'INVITE#'):
            _delete_invitation(self._unit, invitation)
        auditors = DynamoAuditors(self._unit)
        for auditor in auditors.of_team(team_id):
            auditors.remove(team_id, auditor.user_id)
        services = DynamoTeamServices(self._unit, team_id)
        for service in services.all():
            services.delete(service.id)
        self._unit.delete(TEAMS, _name_key(stored.name))
        self._unit.put(team_item(self._unit, team_id) | {'deleted_at': self._clock().isoformat()})

    def members(self, team_id: str) -> list[Member]:
        members = []
        for item in self._unit.query_prefix(team_partition(team_id), 'MEMBER#'):
            profile = _profile(self._unit, item['user_id'])
            members.append(Member(user_id=item['user_id'], joined_on=item['joined_on'],
                                  team_role=item.get('team_role', 'member'),
                                  **{field: profile[field] for field in ('username', 'email', 'first_name', 'last_name')}))
        return sorted(members, key=lambda member: (member.joined_on, member.username))

    def membership(self, user_id: str) -> Membership | None:
        """The user's current membership, if they are in a team."""
        item = current_membership(self._unit, user_id)
        return _membership(self._unit, item) if item else None

    def history(self, user_id: str) -> list[Membership]:
        """All teams the user was in, oldest first."""
        return [_membership(self._unit, item) for item in self._unit.query_prefix(user_partition(user_id), MEMBERSHIP)]

    def stays(self, team_id: str) -> list[Membership]:
        """Everyone who was ever in the team, each stay of theirs, oldest first (`STAY#<membership id>` points to the
        membership in the user's partition)."""
        stays = (self._unit.get(user_partition(item['user_id']), f'{MEMBERSHIP}{item["SK"].removeprefix("STAY#")}')
                 for item in self._unit.query_prefix(team_partition(team_id), 'STAY#'))
        return [_membership(self._unit, stay) for stay in stays if stay]

    def join(self, user_id: str, team_id: str) -> Membership:
        """The user joins the team today, leaving their current team first."""
        team = self.get(team_id)
        self.leave(user_id)
        today = self._clock().date().isoformat()
        membership_id = new_id()
        self._unit.put({'PK': user_partition(user_id), 'SK': f'{MEMBERSHIP}{membership_id}', 'team_id': team_id,
                        'user_id': user_id, 'joined_on': today, 'left_on': None, 'team_role': 'member'})
        self._unit.put({'PK': team_partition(team_id), 'SK': f'MEMBER#{user_id}', 'user_id': user_id, 'joined_on': today,
                        'team_role': 'member'})
        self._unit.put({'PK': team_partition(team_id), 'SK': f'STAY#{membership_id}', 'user_id': user_id})
        return Membership(team_id=team_id, team_name=team.name, user_id=user_id, joined_on=today)

    def leave(self, user_id: str) -> None:
        """The user leaves their team today: the team services their tickets use become personal services (an own
        service with the same short name is used instead of a copy); a team admin's role ends with the membership.
        Many tickets are changed in chunks; the membership ends last, so leaving again completes it."""
        current = current_membership(self._unit, user_id)
        if current is None:
            return
        self._keep_services(user_id, current['team_id'])
        self._unit.put(current | {'left_on': self._clock().date().isoformat()})
        self._unit.delete(team_partition(current['team_id']), f'MEMBER#{user_id}')

    def set_team_role(self, user_id: str, team_role: TeamRole) -> Membership:
        """The role in the team the user is in now (409 if they are in none), on both items of the membership."""
        current = current_membership(self._unit, user_id)
        if current is None:
            raise ConflictError('Only a member of a team has a team role; invite them first')
        member = self._unit.get(team_partition(current['team_id']), f'MEMBER#{user_id}')
        self._unit.put(current | {'team_role': team_role})
        self._unit.put(member | {'team_role': team_role})
        return self.membership(user_id)

    def _keep_services(self, user_id: str, team_id: str) -> None:
        team_services = {service.id: service for service in DynamoTeamServices(self._unit, team_id).all()}
        personal, copies = DynamoServices(self._unit, user_id), {}
        for ticket in self._unit.query_prefix(user_partition(user_id), 'TICKET#'):
            if service := team_services.get(ticket['service_id']):
                if service.id not in copies:
                    copies[service.id] = personal.by_short_name(service.short_name) or personal.add(
                        Service(short_name=service.short_name, name=service.name)).id
                self._unit.make_room(1)
                self._unit.put(ticket | {'service_id': copies[service.id]})

    def _claim(self, name: str, team_id: str) -> None:
        self._unit.put({'PK': TEAMS, 'SK': _name_key(name), 'id': team_id}, unique=f'A team named "{name}" already exists')


def _name_key(name: str) -> str:
    return f'NAME#{name.strip().lower()}'


def _invites_partition(email: str) -> str:
    return f'INVITES#{email.strip().lower()}'


def _delete_invitation(unit: Unit, item: Item) -> None:
    """Both copies of an invitation (`item` is either)."""
    unit.delete(team_partition(item['team_id']), f'INVITE#{item["id"]}')
    unit.delete(_invites_partition(item['email']), team_key(item['team_id']))


class DynamoAuditors:
    """Who has the team view of which team read-only, and until when; kept twice, in the team's partition
    (`AUDITOR#<user id>`) and in the auditor's (`AUDITS#<team id>`)."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit

    def assign(self, auditor: Auditor) -> None:
        """Assigns the user to the team, or changes the end date of an assignment."""
        values = auditor.model_dump(mode='json', exclude={'team_name', 'user_name'})
        self._unit.put({'PK': team_partition(auditor.team_id), 'SK': f'AUDITOR#{auditor.user_id}', **values})
        self._unit.put({'PK': user_partition(auditor.user_id), 'SK': f'AUDITS#{auditor.team_id}', **values})

    def remove(self, team_id: str, user_id: str) -> None:
        if self._unit.get(team_partition(team_id), f'AUDITOR#{user_id}') is None:
            raise NotFoundError('No such auditor')
        self._unit.delete(team_partition(team_id), f'AUDITOR#{user_id}')
        self._unit.delete(user_partition(user_id), f'AUDITS#{team_id}')

    def all(self) -> list[Auditor]:
        teams = [item['id'] for item in self._unit.query_prefix(TEAMS, 'TEAM#') if item['deleted_at'] is None]
        return _sorted([auditor for team_id in teams for auditor in self.of_team(team_id)])

    def of_user(self, user_id: str) -> list[Auditor]:
        return _sorted([self._auditor(item) for item in self._unit.query_prefix(user_partition(user_id), 'AUDITS#')])

    def of_team(self, team_id: str) -> list[Auditor]:
        return _sorted([self._auditor(item) for item in self._unit.query_prefix(team_partition(team_id), 'AUDITOR#')])

    def _auditor(self, item: Item) -> Auditor:
        profile = _profile(self._unit, item['user_id']) or {}
        name = f'{profile.get("first_name", "")} {profile.get("last_name", "")}'.strip()
        return Auditor(**attributes(item), team_name=team_item(self._unit, item['team_id'])['name'], user_name=name)


def _sorted(auditors: list[Auditor]) -> list[Auditor]:
    return sorted(auditors, key=lambda auditor: (auditor.team_name.lower(), auditor.user_name))


class DynamoInvitations:
    """Invitations to a team by e-mail address; the invited user accepts or declines them."""

    def __init__(self, unit: Unit, clock: Callable[[], dt.datetime] | None = None) -> None:
        self._unit = unit
        self._clock = clock or dt.datetime.now

    def invite(self, team_id: str, email: str, invited_by: str) -> None:
        """Invite whoever has this e-mail address (ignoring case); nothing tells whether such a user exists. Members
        of the team and users already invited are left as they are."""
        email = email.strip()
        members = DynamoTeams(self._unit).members(team_id)
        if any(member.email.lower() == email.lower() for member in members) or self._unit.get(
                _invites_partition(email), team_key(team_id)):
            return
        invitation = Invitation(id=new_id(), team_id=team_id, email=email, invited_by=invited_by,
                                invited_at=self._clock())
        values = invitation.model_dump(mode='json', exclude={'team_name'})
        self._unit.put({'PK': team_partition(team_id), 'SK': f'INVITE#{invitation.id}', **values})
        self._unit.put({'PK': _invites_partition(email), 'SK': team_key(team_id), **values})

    def of_team(self, team_id: str) -> list[Invitation]:
        return self._invitations(self._unit.query_prefix(team_partition(team_id), 'INVITE#'))

    def withdraw(self, team_id: str, invitation_id: str) -> None:
        item = self._unit.get(team_partition(team_id), f'INVITE#{invitation_id}')
        if item is None:
            raise NotFoundError(f'No open invitation with id {invitation_id}')
        _delete_invitation(self._unit, item)

    def of_user(self, user_id: str) -> list[Invitation]:
        """The open invitations to the user's e-mail address (of teams that still exist)."""
        profile = _profile(self._unit, user_id)
        items = self._unit.query_prefix(_invites_partition(profile['email']), 'TEAM#') if profile else []
        return self._invitations(item for item in items if team_item(self._unit, item['team_id'])['deleted_at'] is None)

    def accept(self, user_id: str, invitation_id: str, teams: Teams) -> Membership:
        """The user joins the team (leaving their current one); their other invitations are declined."""
        invitation = self._own(user_id, invitation_id)
        membership = teams.join(user_id, invitation.team_id)
        for item in self._unit.query_prefix(_invites_partition(invitation.email), 'TEAM#'):
            _delete_invitation(self._unit, item)
        return membership

    def decline(self, user_id: str, invitation_id: str) -> None:
        invitation = self._own(user_id, invitation_id)
        _delete_invitation(self._unit, invitation.model_dump())

    def _own(self, user_id: str, invitation_id: str) -> Invitation:
        """One of the user's open invitations; another user's is unknown (404)."""
        for invitation in self.of_user(user_id):
            if invitation.id == invitation_id:
                return invitation
        raise NotFoundError(f'No open invitation with id {invitation_id}')

    def _invitations(self, items: object) -> list[Invitation]:
        invitations = [Invitation(**attributes(item), team_name=team_item(self._unit, item['team_id'])['name'])
                       for item in items]
        return sorted(invitations, key=lambda invitation: (invitation.invited_at, invitation.id))


class DynamoReportViews:
    """Which team admin looked at which report of a member, and when; the member sees it in their settings."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit

    def add(self, view: ReportView) -> None:
        view_id = new_id()
        sort_key = f'VIEW#{view.viewed_at:%Y-%m-%dT%H:%M:%S.%f}#{view_id}'  # in time order
        self._unit.put({'PK': user_partition(view.member_id), 'SK': sort_key,
                        **view.model_dump(mode='json', exclude={'viewer_name'})})

    def of_member(self, member_id: str, limit: int = 50) -> list[ReportView]:
        """The latest views of the member's reports, newest first."""
        views = []
        for item in self._unit.newest(user_partition(member_id), 'VIEW#', limit):
            if viewer := _profile(self._unit, item['viewer_id']):
                name = f'{viewer["first_name"]} {viewer["last_name"]}'.strip()
                views.append(ReportView(**attributes(item), viewer_name=name))
        return views
