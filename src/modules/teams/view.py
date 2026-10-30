"""Team view (TASKS.md L.10): whose data a request shows. A team admin views the members of their team read-only, from
the day they joined it; each report viewed is logged for the member."""

import datetime as dt
from dataclasses import dataclass

import falcon
from pydantic import BaseModel, Field

from src.models.teams import Membership, ReportView
from src.modules.auth.sessions import current_user
from src.modules.storage.errors import NotFoundError
from src.modules.storage.store import Store
from src.utils.api import PeriodQuery

_MEMBER = Field(default=None, description="Team view: id (UUID) of a member of the team admin's team")


class MemberQuery(BaseModel):
    member: str | None = _MEMBER


class MemberPeriodQuery(PeriodQuery):
    member: str | None = _MEMBER


@dataclass(frozen=True)
class Viewing:
    """The user whose data a request shows; in the team view also who looks and the member's first day in the team."""

    user_id: str
    viewer_id: str | None = None
    visible_from: dt.date | None = None

    @property
    def team_view(self) -> bool:
        return self.viewer_id is not None

    def log(self, store: Store, report: str, period: str, now: dt.datetime) -> None:
        """In the team view, record for the member which report was looked at."""
        if self.team_view:
            store.report_views().add(ReportView(member_id=self.user_id, viewer_id=self.viewer_id, report=report,
                                                period=period, viewed_at=now))


def viewing(req: falcon.Request, store: Store, member: str | None) -> Viewing:
    """The current user's own data, or with `member` a member of the team the current user is team admin of (403
    otherwise: other users, former members, admins who are not team admin of that team)."""
    user_id = current_user(req)
    if member is None or member == user_id:
        return Viewing(user_id)
    membership = _membership_in_own_team(store, user_id, member)
    if membership is None:
        raise falcon.HTTPForbidden(description="Only the team admins of the member's team can view their data")
    return Viewing(member, user_id, membership.joined_on)


def _membership_in_own_team(store: Store, user_id: str, member: str) -> Membership | None:
    """The member's membership if they are in the team the user is team admin of."""
    teams = store.teams()
    own, theirs = teams.membership(user_id), teams.membership(member)
    same_team = own is not None and theirs is not None and own.team_id == theirs.team_id
    return theirs if same_team and _role(store, user_id) == 'team_admin' else None


def _role(store: Store, user_id: str) -> str | None:
    try:
        return store.users().get(user_id).role
    except NotFoundError:  # e.g. no user yet with the login off
        return None
