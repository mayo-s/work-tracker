"""Users and app-wide settings as shown and entered on the admin page: accounts only, nothing of anyone's time data."""

import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from src.models.teams import Auditor, Member, Membership, Team, TeamRole
from src.models.users import AssignableRole, Role, User


class AdminUserView(BaseModel):
    id: str = Field(description='Random UUID')
    username: str
    email: str
    first_name: str
    last_name: str
    role: Role
    active: bool = Field(description='False: deactivated, cannot log in')
    registered_at: dt.datetime | None = Field(description='Null for users registered before it was recorded')
    last_login_at: dt.datetime | None
    team: str | None = Field(description='Name of the team the user is in')
    team_role: TeamRole | None = Field(description='Their role in that team; null without a team')
    must_change_password: bool = Field(description='A one-time password is set; the user has not chosen their own yet')

    @classmethod
    def of(cls, user: User, membership: Membership | None) -> Self:
        return cls(**user.model_dump(), team=membership.team_name if membership else None,
                   team_role=membership.team_role if membership else None)


class AdminUserInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    role: AssignableRole = Field(description='The app role: admins manage users and teams (root is never given)')
    team_role: TeamRole | None = Field(default=None, description='The role in their team (only for a member of a team); '
                                                                 'null keeps it. A team admin manages the team')
    active: bool = Field(description='False deactivates the user: they cannot log in, their sessions end')


class AdminSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')

    registration: bool = Field(description='Whether new users can register on /register (off by default)')


class AdminTeamView(BaseModel):
    id: str
    name: str
    members: int = Field(description='Number of current members')
    team_admins: list[str] = Field(description='Usernames of the team admins')

    @classmethod
    def of(cls, team: Team, members: list[Member]) -> Self:
        return cls(id=team.id, name=team.name, members=len(members),
                   team_admins=[member.username for member in members if member.team_role == 'team_admin'])


class AuditorInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    until: dt.date | None = Field(default=None, description='The last day the auditor sees the team; null: until removed')


class AuditorView(BaseModel):
    team_id: str
    team: str
    user_id: str
    user: str = Field(description='Name of the auditor')
    until: dt.date | None
    assigned_at: dt.datetime

    @classmethod
    def of(cls, auditor: Auditor) -> Self:
        return cls(team_id=auditor.team_id, team=auditor.team_name, user_id=auditor.user_id, user=auditor.user_name,
                   until=auditor.until, assigned_at=auditor.assigned_at)


class OneTimePasswordView(BaseModel):
    password: str = Field(description='Shown only now: the admin gives it to the user, who chooses their own at the next '
                                      'login', examples=['k7Qm-3xTp-9wLs-Rf2c'])
