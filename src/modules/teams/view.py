"""Team view (TASKS.md 7.4, 9.1e): whose data a request shows. A team admin views the current members of their team
read-only, from the day they joined it; an auditor everyone who was ever in the teams they audit, for the days of each
stay. Each report viewed is logged for the member."""

import datetime as dt
from dataclasses import dataclass

import falcon
from pydantic import BaseModel, Field

from src.lib.stays import Period, Stays
from src.lib.texts import text
from src.models.teams import ReportView
from src.modules.auth.sessions import current_user
from src.modules.storage.store import Store
from src.utils.api import PeriodQuery

_MEMBER = Field(default=None, description="Team view: id (UUID) of a member of the team admin's or auditor's team")


class MemberQuery(BaseModel):
    member: str | None = _MEMBER


class MemberPeriodQuery(PeriodQuery):
    member: str | None = _MEMBER


@dataclass(frozen=True)
class Viewing:
    """The user whose data a request shows; in the team view also who looks and the member's days shown."""

    user_id: str
    viewer_id: str | None = None
    stays: Stays | None = None

    @property
    def team_view(self) -> bool:
        return self.viewer_id is not None

    def log(self, store: Store, report: str, period: str, now: dt.datetime) -> None:
        """In the team view, record for the member which report was looked at."""
        if self.team_view:
            store.report_views().add(ReportView(member_id=self.user_id, viewer_id=self.viewer_id, report=report,
                                                period=period, viewed_at=now))


def viewing(req: falcon.Request, store: Store, member: str | None, today: dt.date | None = None) -> Viewing:
    """The current user's own data, or with `member` the data of a current member of the team the current user is team
    admin of, or of anyone who was in a team they audit (403 otherwise: other users, former members, admins who are
    neither)."""
    user_id = current_user(req)
    if member is None or member == user_id:
        return Viewing(user_id)
    periods = _as_team_admin(store, user_id, member) + _as_auditor(store, user_id, member, today or dt.date.today())
    if not periods:
        raise falcon.HTTPForbidden(
            description=text("Only the team admins and auditors of the member's team can view their data"))
    return Viewing(member, user_id, Stays(periods))


def _as_team_admin(store: Store, user_id: str, member: str) -> tuple[Period, ...]:
    """The member's current stay if they are in the team the user is team admin of."""
    teams = store.teams()
    own, theirs = teams.membership(user_id), teams.membership(member)
    same_team = own is not None and theirs is not None and own.team_id == theirs.team_id
    return ((theirs.joined_on, None),) if same_team and own.team_role == 'team_admin' else ()


def _as_auditor(store: Store, user_id: str, member: str, today: dt.date) -> tuple[Period, ...]:
    """The member's stays in the teams the user audits today."""
    audited = {auditor.team_id for auditor in store.auditors().of_user(user_id) if auditor.active(today)}
    return tuple((stay.joined_on, stay.left_on) for stay in store.teams().history(member) if stay.team_id in audited)


@dataclass(frozen=True)
class TeamPerson:
    user_id: str
    stays: Stays


@dataclass(frozen=True)
class TeamScope:
    """Whom the team report counts for the current user, and whether that is only the team's current members."""

    people: tuple[TeamPerson, ...]
    current_only: bool


def team_scope(req: falcon.Request, store: Store, team_id: str, today: dt.date) -> TeamScope:
    """By the rules of the team view: an active auditor of the team has everyone who was ever in it, for the days of
    each stay; a team admin of the team its current members, from the day they joined. 403 otherwise, whether the team
    exists or not."""
    user_id = current_user(req)
    audits = _audits(store, user_id, team_id, today)
    if not audits and not _is_team_admin_of(store, user_id, team_id):
        raise falcon.HTTPForbidden(description=text('Only the team admins and auditors of this team can view its report'))
    return TeamScope(_people(store, team_id, audits), not audits)


def _audits(store: Store, user_id: str, team_id: str, today: dt.date) -> bool:
    return any(auditor.team_id == team_id and auditor.active(today) for auditor in store.auditors().of_user(user_id))


def _is_team_admin_of(store: Store, user_id: str, team_id: str) -> bool:
    own = store.teams().membership(user_id)
    return own is not None and own.team_id == team_id and own.team_role == 'team_admin'


def _people(store: Store, team_id: str, former_too: bool) -> tuple[TeamPerson, ...]:
    periods: dict[str, list[Period]] = {}
    for stay in store.teams().stays(team_id):
        if former_too or stay.left_on is None:
            periods.setdefault(stay.user_id, []).append((stay.joined_on, stay.left_on))
    return tuple(TeamPerson(user_id, Stays(tuple(person))) for user_id, person in periods.items())
