"""Teams as shown and entered in the API: accounts of the members only, nothing of their time data."""

import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from src.models.teams import Invitation, Member, Membership, ReportView, Team
from src.models.users import EMAIL_PATTERN, Role, User


class TeamInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=50, examples=['Platform'])

    def to_team(self, team_id: int | None = None) -> Team:
        return Team(id=team_id, name=self.name)


class MemberView(BaseModel):
    user_id: str
    username: str
    email: str
    first_name: str
    last_name: str
    role: Role
    joined_on: dt.date

    @classmethod
    def of(cls, member: Member) -> Self:
        return cls(**member.model_dump())


class InvitationView(BaseModel):
    id: int
    email: str
    invited_at: dt.datetime

    @classmethod
    def of(cls, invitation: Invitation) -> Self:
        return cls(**invitation.model_dump(include={'id', 'email', 'invited_at'}))


class TeamPageView(BaseModel):
    """A team as its admins see it: members and open invitations."""

    id: int
    name: str
    members: list[MemberView]
    invitations: list[InvitationView]


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    email: str = Field(pattern=EMAIL_PATTERN, max_length=200, description='The exact e-mail address (ignoring case)')


class InvitationSent(BaseModel):
    message: str = Field(description='The same whether a user with this e-mail address exists or not')


class TeamRef(BaseModel):
    id: int
    name: str
    joined_on: dt.date

    @classmethod
    def of(cls, membership: Membership) -> Self:
        return cls(id=membership.team_id, name=membership.team_name, joined_on=membership.joined_on)


class MyInvitationView(BaseModel):
    id: int
    team_name: str
    invited_at: dt.datetime
    invited_by: str = Field(description='Name of the inviting admin')

    @classmethod
    def of(cls, invitation: Invitation, inviter: User) -> Self:
        return cls(id=invitation.id, team_name=invitation.team_name, invited_at=invitation.invited_at,
                   invited_by=' '.join(filter(None, (inviter.first_name, inviter.last_name))))


class ReportViewEntry(BaseModel):
    viewer: str = Field(description='Name of the team admin who looked')
    report: str = Field(description='dashboard, week, month or year')
    period: str = Field(description='e.g. 2026-W44, 2026-10, 2026; empty for the dashboard')
    viewed_at: dt.datetime

    @classmethod
    def of(cls, view: ReportView) -> Self:
        return cls(viewer=view.viewer_name, report=view.report, period=view.period, viewed_at=view.viewed_at)


class MyTeamView(BaseModel):
    """The user's team (null without one), their open invitations, who can see their reports and who looked."""

    team: TeamRef | None
    invitations: list[MyInvitationView]
    team_admins: list[str] = Field(description='Names of the team admins who can see your reports')
    viewed_by: list[ReportViewEntry] = Field(description='The latest views of your reports, newest first')
