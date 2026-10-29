"""Teams, their members (kept as history: which team a user was in on each day) and invitations."""

import datetime as dt
from typing import Literal

from pydantic import Field

from src.models.base import DomainModel
from src.models.users import Role


class Team(DomainModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=50, description='e.g. Platform')


class Membership(DomainModel):
    """A user in a team from `joined_on` until the day before `left_on` (None: still a member)."""

    team_id: int
    team_name: str
    user_id: str
    joined_on: dt.date
    left_on: dt.date | None = None


class Member(DomainModel):
    """A current member as their team sees them: the account, none of the time data."""

    user_id: str
    username: str
    email: str
    first_name: str
    last_name: str
    role: Role
    joined_on: dt.date


class Invitation(DomainModel):
    """An invitation to the user with this e-mail address, whether such a user exists or not."""

    id: int | None = None
    team_id: int
    team_name: str = ''
    email: str
    invited_by: str
    invited_at: dt.datetime


class ReportView(DomainModel):
    """A team admin looked at a report of a member (team view)."""

    member_id: str
    viewer_id: str
    viewer_name: str = ''
    report: Literal['dashboard', 'week', 'month', 'year']
    period: str = Field(default='', description='e.g. 2026-W44, 2026-10, 2026; empty for the dashboard')
    viewed_at: dt.datetime
