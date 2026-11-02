"""The SQLite backend of the storage interfaces (store.py): this package's repositories on one connection."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from src.models.settings import Settings
from src.modules.storage.audit import AuditLogRepository
from src.modules.storage.catalog import ActivityTypeRepository, ServiceRepository, TeamServiceRepository
from src.modules.storage.database import Database
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.owners import clear_records
from src.modules.storage.pto_years import PtoYearRepository
from src.modules.storage.renames import rename_ticket
from src.modules.storage.schedules import ScheduleRepository
from src.modules.storage.settings import (
    finish_setup, import_unfinished, load_settings, load_theme, registration_open, save_settings, save_theme,
    set_registration, setup_done, start_import,
)
from src.modules.storage.store import Clock, RenameResult, Theme
from src.modules.storage.teams import InvitationRepository, ReportViewLog, TeamRepository
from src.modules.storage.tickets import TicketRepository
from src.modules.storage.users import LoginAttempts, SessionRepository, UserRepository


class SqliteStore:
    """The repositories and settings within the transaction of one connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def days(self, user_id: str) -> DayRepository:
        return DayRepository(self._conn, user_id)

    def entries(self, user_id: str, clock: Clock | None = None) -> EntryRepository:
        return EntryRepository(self._conn, user_id, clock)

    def tickets(self, user_id: str) -> TicketRepository:
        return TicketRepository(self._conn, user_id)

    def services(self, user_id: str) -> ServiceRepository:
        return ServiceRepository(self._conn, user_id)

    def team_services(self, team_id: int) -> TeamServiceRepository:
        return TeamServiceRepository(self._conn, team_id)

    def activity_types(self, user_id: str) -> ActivityTypeRepository:
        return ActivityTypeRepository(self._conn, user_id)

    def schedules(self, user_id: str) -> ScheduleRepository:
        return ScheduleRepository(self._conn, user_id)

    def pto_years(self, user_id: str) -> PtoYearRepository:
        return PtoYearRepository(self._conn, user_id)

    def users(self, clock: Clock | None = None) -> UserRepository:
        return UserRepository(self._conn, clock)

    def sessions(self) -> SessionRepository:
        return SessionRepository(self._conn)

    def attempts(self) -> LoginAttempts:
        return LoginAttempts(self._conn)

    def teams(self, clock: Clock | None = None) -> TeamRepository:
        return TeamRepository(self._conn, clock)

    def invitations(self, clock: Clock | None = None) -> InvitationRepository:
        return InvitationRepository(self._conn, clock)

    def report_views(self) -> ReportViewLog:
        return ReportViewLog(self._conn)

    def audit_log(self) -> AuditLogRepository:
        return AuditLogRepository(self._conn)

    def rename_ticket(self, user_id: str, old_key: str, new_key: str, clock: Clock | None = None) -> RenameResult:
        return rename_ticket(self._conn, user_id, old_key, new_key, clock)

    def load_settings(self, user_id: str) -> Settings:
        return load_settings(self._conn, user_id)

    def save_settings(self, user_id: str, settings: Settings) -> None:
        save_settings(self._conn, user_id, settings)

    def setup_done(self, user_id: str) -> bool:
        return setup_done(self._conn, user_id)

    def finish_setup(self, user_id: str) -> None:
        finish_setup(self._conn, user_id)

    def start_import(self, user_id: str) -> None:
        start_import(self._conn, user_id)

    def import_unfinished(self, user_id: str) -> bool:
        return import_unfinished(self._conn, user_id)

    def clear_records(self, user_id: str) -> None:
        clear_records(self._conn, user_id)

    def make_room(self, items: int) -> None:
        """Nothing to do: one SQLite transaction holds any number of changes."""

    def load_theme(self, user_id: str) -> Theme:
        return load_theme(self._conn, user_id)

    def save_theme(self, user_id: str, theme: Theme) -> None:
        save_theme(self._conn, user_id, theme)

    def registration_open(self) -> bool:
        return registration_open(self._conn)

    def set_registration(self, enabled: bool) -> None:
        set_registration(self._conn, enabled)


class SqliteStorage:
    """A SQLite database file as storage backend."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[SqliteStore]:
        """Commit when the block succeeds, roll back when it raises."""
        with self.database.transaction() as conn:
            yield SqliteStore(conn)

    def migrate(self) -> int:
        return self.database.migrate()
