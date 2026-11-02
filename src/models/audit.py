"""The audit log (SPEC 5.7): who changed what of whom and when in running the app; none of anyone's time data."""

import datetime as dt
from typing import Literal

from pydantic import Field

from src.models.base import DomainModel

AuditAction = Literal[
    'root_created', 'role_changed', 'team_role_changed', 'deactivated', 'reactivated', 'one_time_password',
    'registration_switched', 'team_created', 'team_renamed', 'team_deleted', 'member_removed', 'auditor_assigned',
    'auditor_removed', 'root_login_reset',
]


class AuditEntry(DomainModel):
    """One change; the names are filled in when the log is read (users are never deleted, teams stay)."""

    actor_id: str
    action: AuditAction
    user_id: str | None = Field(default=None, description='Whose account the change is about')
    team_id: str | None = None
    detail: str = Field(default='', description="e.g. the new role, 'on' or 'off', a team's former name, an auditor's "
                                                "last day")
    at: dt.datetime
    actor_name: str = ''
    user_name: str = ''
    team_name: str = ''
