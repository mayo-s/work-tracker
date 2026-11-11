"""Teams as shown and entered in the API: accounts of the members only, nothing of their time data."""

import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from src.models.teams import Auditor, Invitation, Member, Membership, ReportView, Team, TeamRole
from src.models.users import DELETED_USER, EMAIL_PATTERN, User
from src.modules.pages.languages import PersonName


class TeamInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=50, examples=['Platform'])

    def to_team(self, team_id: str | None = None) -> Team:
        return Team(id=team_id, name=self.name)


class MemberView(BaseModel):
    user_id: str
    username: str
    email: str
    first_name: str
    last_name: str
    team_role: TeamRole
    joined_on: dt.date

    @classmethod
    def of(cls, member: Member) -> Self:
        return cls(**member.model_dump())


class InvitationView(BaseModel):
    id: str
    email: str
    invited_at: dt.datetime

    @classmethod
    def of(cls, invitation: Invitation) -> Self:
        return cls(**invitation.model_dump(include={'id', 'email', 'invited_at'}))


class TeamPageView(BaseModel):
    """A team as its admins see it: members and open invitations."""

    id: str
    name: str
    members: list[MemberView]
    invitations: list[InvitationView]


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    email: str = Field(pattern=EMAIL_PATTERN, max_length=200, description='The exact e-mail address (ignoring case)')


class InvitationSent(BaseModel):
    message: str = Field(description='The same whether a user with this e-mail address exists or not')


class TeamRef(BaseModel):
    id: str
    name: str
    joined_on: dt.date
    team_role: TeamRole = Field(description='member or team_admin (manages the team, has its team view)')

    @classmethod
    def of(cls, membership: Membership) -> Self:
        return cls(id=membership.team_id, name=membership.team_name, joined_on=membership.joined_on,
                   team_role=membership.team_role)


class MyInvitationView(BaseModel):
    id: str
    team_name: str
    invited_at: dt.datetime
    invited_by: PersonName = Field(description='Name of the inviting admin, "Deleted user" once their account is deleted')

    @classmethod
    def of(cls, invitation: Invitation, inviter: User | None) -> Self:
        return cls(id=invitation.id, team_name=invitation.team_name, invited_at=invitation.invited_at,
                   invited_by=inviter.full_name if inviter else DELETED_USER)


class AuditorNote(BaseModel):
    name: str = Field(description='Name of the auditor')
    team: str = Field(description='The team whose view they have, one you are or were in')
    until: dt.date | None = Field(description='The last day; null: until removed')

    @classmethod
    def of(cls, auditor: Auditor) -> Self:
        return cls(name=auditor.user_name, team=auditor.team_name, until=auditor.until)


class StayView(BaseModel):
    joined_on: dt.date
    left_on: dt.date | None = Field(description='The first day no longer in the team; null: still in it')


class AuditedMember(BaseModel):
    user_id: str
    name: str
    stays: list[StayView] = Field(description='The days shown in the team view: each stay in the team, oldest first')


class AuditedTeam(BaseModel):
    """A team the user audits, with everyone who was ever in it."""

    team_id: str
    team: str
    until: dt.date | None = Field(description='The last day of the assignment; null: until removed')
    members: list[AuditedMember]


class ReportViewEntry(BaseModel):
    viewer: PersonName = Field(description='Name of the team admin or auditor who looked, "Deleted user" once their '
                                           'account is deleted')
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
    auditors: list[AuditorNote] = Field(default=[], description='Auditors who can see your days in a team')
    viewed_by: list[ReportViewEntry] = Field(description='The latest views of your reports, newest first')
