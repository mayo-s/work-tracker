"""Users and app-wide settings as shown and entered on the admin page: accounts only, nothing of anyone's time data."""

import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from src.models.teams import Team
from src.models.users import Role, User


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

    @classmethod
    def of(cls, user: User, team: str | None) -> Self:
        return cls(**user.model_dump(), team=team)


class AdminUserInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    role: Role = Field(description='A team admin manages the team they are in')
    active: bool = Field(description='False deactivates the user: they cannot log in, their sessions end')


class AdminSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')

    registration: bool = Field(description='Whether new users can register on /register (off by default)')


class AdminTeamView(BaseModel):
    id: int
    name: str
    members: int = Field(description='Number of current members')
    team_admins: list[str] = Field(description='Usernames of the team admins')

    @classmethod
    def of(cls, team: Team, members: list[tuple[str, str]]) -> Self:
        """`members`: username and role of each current member."""
        return cls(id=team.id, name=team.name, members=len(members),
                   team_admins=[username for username, role in members if role == 'team_admin'])
