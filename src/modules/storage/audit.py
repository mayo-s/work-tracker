"""The audit log on SQLite; works within the transaction of the given connection."""

import sqlite3

from src.models.audit import AuditEntry
from src.models.base import new_id
from src.models.users import DELETED_USER

_SELECT = (
    "SELECT actor_id, action, user_id, team_id, detail, at,"
    f" COALESCE(trim(actor.first_name || ' ' || actor.last_name), '{DELETED_USER}') AS actor_name,"
    " COALESCE(trim(about.first_name || ' ' || about.last_name), '') AS user_name, COALESCE(teams.name, '') AS team_name"
    ' FROM audit_log LEFT JOIN users AS actor ON actor.id = actor_id LEFT JOIN users AS about ON about.id = user_id'
    ' LEFT JOIN teams ON teams.id = team_id'
)


class AuditLogRepository:
    """Who changed what of whom and when; root and admins read it all, every user the entries about them."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, entry: AuditEntry) -> None:
        self._conn.execute('INSERT INTO audit_log (id, at, actor_id, action, user_id, team_id, detail)'
                           ' VALUES (?, ?, ?, ?, ?, ?, ?)', (new_id(), entry.at.isoformat(), entry.actor_id, entry.action,
                                                             entry.user_id, entry.team_id, entry.detail))

    def latest(self, limit: int = 200) -> list[AuditEntry]:
        """The latest entries, newest first."""
        rows = self._conn.execute(f'{_SELECT} ORDER BY at DESC, audit_log.id DESC LIMIT ?', (limit,))
        return [AuditEntry(**dict(row)) for row in rows]

    def of_user(self, user_id: str, limit: int = 50) -> list[AuditEntry]:
        """The latest entries about the user's account, newest first."""
        rows = self._conn.execute(f'{_SELECT} WHERE user_id = ? ORDER BY at DESC, audit_log.id DESC LIMIT ?',
                                  (user_id, limit))
        return [AuditEntry(**dict(row)) for row in rows]

    def all(self) -> list[AuditEntry]:
        """All entries, oldest first (for the full backup)."""
        return [AuditEntry(**dict(row)) for row in self._conn.execute(f'{_SELECT} ORDER BY at, audit_log.id')]
