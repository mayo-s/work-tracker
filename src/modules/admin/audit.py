"""Recording changes in the audit log (SPEC 5.7), and how an entry is shown."""

import datetime as dt
from typing import Self

from pydantic import BaseModel, Field

from src.models.audit import AuditAction, AuditEntry
from src.modules.storage.store import Store


def record(store: Store, at: dt.datetime, actor_id: str, action: AuditAction, user_id: str | None = None,
           team_id: str | None = None, detail: str = '') -> None:
    """Log a change in the same transaction as the change itself, so one is not kept without the other."""
    store.audit_log().add(AuditEntry(actor_id=actor_id, action=action, user_id=user_id, team_id=team_id, detail=detail,
                                     at=at))


class AuditView(BaseModel):
    at: dt.datetime
    actor: str = Field(description='Name of who made the change')
    action: AuditAction
    user: str | None = Field(description='Name of whose account it is about')
    team: str | None = Field(description='Name of the team (now, after a rename)')
    detail: str = Field(description="e.g. the new role, 'on' or 'off', a team's former name, an auditor's last day")

    @classmethod
    def of(cls, entry: AuditEntry) -> Self:
        return cls(at=entry.at, actor=entry.actor_name, action=entry.action, user=entry.user_name or None,
                   team=entry.team_name or None, detail=entry.detail)
