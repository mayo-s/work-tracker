"""The DynamoDB backend of the storage interfaces (store.py), used on AWS Lambda; where the items are: keys.py."""

import datetime as dt
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from src.models.settings import Settings
from src.modules.storage.dynamodb.audit import DynamoAuditLog
from src.modules.storage.dynamodb import settings as stored_settings
from src.modules.storage.dynamodb.catalog import DynamoActivityTypes, DynamoServices, DynamoTeamServices
from src.modules.storage.dynamodb.days import DynamoDays
from src.modules.storage.dynamodb.entries import DynamoEntries
from src.modules.storage.dynamodb.entry_kinds import to_one_kind
from src.modules.storage.dynamodb.flag_removal import drop_flags
from src.modules.storage.dynamodb.keys import APP, META, SCHEMA, user_partition
from src.modules.storage.dynamodb.messages import DynamoMessages
from src.modules.storage.dynamodb.purge import delete_user, purge
from src.modules.storage.dynamodb.renames import rename_ticket
from src.modules.storage.dynamodb.schedules import DynamoPtoYears, DynamoSchedules
from src.modules.storage.dynamodb.table import Table
from src.modules.storage.dynamodb.teams import DynamoAuditors, DynamoInvitations, DynamoReportViews, DynamoTeams
from src.modules.storage.dynamodb.tickets import DynamoTickets
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.dynamodb.users import DynamoAttempts, DynamoBrowsers, DynamoSessions, DynamoUsers
from src.modules.storage.errors import USED_TOKEN, SchemaVersionError
from src.modules.storage.store import Clock, Language, RenameResult, Theme

# Changes of the item layout, applied once in order: MIGRATIONS[0] brings a table from version 1 to 2, and so on
MIGRATIONS: list[Callable[[Table], None]] = [
    to_one_kind,  # 2: one kind of entry (TASKS.md 13.7)
    drop_flags,  # 3: the review flags of the former spreadsheet import go (TASKS.md L.12)
]
LATEST = 1 + len(MIGRATIONS)
# The kinds of a user's own records in their partition (not their settings, sessions, memberships or report views)
RECORDS = ('DAY#', 'ENTRY#', 'ENTRY_ID#', 'HISTORY#', 'TICKET#', 'SERVICE#', 'SERVICE_NAME#', 'ACTIVITY_TYPE#',
           'ACTIVITY_TYPE_NAME#', 'SCHEDULE#', 'SCHEDULE_FROM#', 'PTO#')


class DynamoStore:
    """The repositories and settings within one transaction on the table."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit

    def days(self, user_id: str) -> DynamoDays:
        return DynamoDays(self._unit, user_id)

    def entries(self, user_id: str, clock: Clock | None = None) -> DynamoEntries:
        return DynamoEntries(self._unit, user_id, clock)

    def tickets(self, user_id: str) -> DynamoTickets:
        return DynamoTickets(self._unit, user_id)

    def services(self, user_id: str) -> DynamoServices:
        return DynamoServices(self._unit, user_id)

    def team_services(self, team_id: str) -> DynamoTeamServices:
        return DynamoTeamServices(self._unit, team_id)

    def activity_types(self, user_id: str) -> DynamoActivityTypes:
        return DynamoActivityTypes(self._unit, user_id)

    def schedules(self, user_id: str) -> DynamoSchedules:
        return DynamoSchedules(self._unit, user_id)

    def pto_years(self, user_id: str) -> DynamoPtoYears:
        return DynamoPtoYears(self._unit, user_id)

    def users(self, clock: Clock | None = None) -> DynamoUsers:
        return DynamoUsers(self._unit, clock)

    def sessions(self) -> DynamoSessions:
        return DynamoSessions(self._unit)

    def browsers(self) -> DynamoBrowsers:
        return DynamoBrowsers(self._unit)

    def attempts(self) -> DynamoAttempts:
        return DynamoAttempts(self._unit)

    def teams(self, clock: Clock | None = None) -> DynamoTeams:
        return DynamoTeams(self._unit, clock)

    def invitations(self, clock: Clock | None = None) -> DynamoInvitations:
        return DynamoInvitations(self._unit, clock)

    def report_views(self) -> DynamoReportViews:
        return DynamoReportViews(self._unit)

    def audit_log(self) -> DynamoAuditLog:
        return DynamoAuditLog(self._unit)

    def auditors(self) -> DynamoAuditors:
        return DynamoAuditors(self._unit)

    def messages(self) -> DynamoMessages:
        return DynamoMessages(self._unit)

    def rename_ticket(self, user_id: str, old_key: str, new_key: str, clock: Clock | None = None) -> RenameResult:
        return rename_ticket(self._unit, user_id, old_key, new_key, clock)

    def load_settings(self, user_id: str) -> Settings:
        return stored_settings.load_settings(self._unit, user_id)

    def save_settings(self, user_id: str, settings: Settings) -> None:
        stored_settings.save_settings(self._unit, user_id, settings)

    def setup_done(self, user_id: str) -> bool:
        return stored_settings.setup_done(self._unit, user_id)

    def finish_setup(self, user_id: str) -> None:
        stored_settings.finish_setup(self._unit, user_id)

    def start_import(self, user_id: str) -> None:
        stored_settings.start_import(self._unit, user_id)

    def import_unfinished(self, user_id: str) -> bool:
        return stored_settings.import_unfinished(self._unit, user_id)

    def clear_records(self, user_id: str) -> None:
        """The user's own records go (in chunks), their account and settings stay."""
        pk = user_partition(user_id)
        for prefix in RECORDS:
            for item in self._unit.query_prefix(pk, prefix):
                self._unit.make_room(1)
                self._unit.delete(pk, item['SK'])

    def make_room(self, items: int) -> None:
        self._unit.make_room(items)

    def load_theme(self, user_id: str) -> Theme:
        return stored_settings.load_theme(self._unit, user_id)

    def save_theme(self, user_id: str, theme: Theme) -> None:
        stored_settings.save_theme(self._unit, user_id, theme)

    def load_language(self, user_id: str) -> Language | None:
        return stored_settings.load_language(self._unit, user_id)

    def save_language(self, user_id: str, language: Language) -> None:
        stored_settings.save_language(self._unit, user_id, language)

    def registration_open(self) -> bool:
        return stored_settings.registration_open(self._unit)

    def set_registration(self, enabled: bool) -> None:
        stored_settings.set_registration(self._unit, enabled)

    def use_setup_token(self, token_hash: str, at: dt.datetime) -> None:
        """Marks the setup token used (by its hash): it works only once (409 for a second time)."""
        self._unit.put({'PK': APP, 'SK': f'TOKEN#{token_hash}', 'used_at': at.isoformat()}, unique=USED_TOKEN)

    def delete_user(self, user_id: str) -> None:
        """The user goes with everything of theirs (in chunks)."""
        delete_user(self._unit, user_id)

    def purge(self, root_id: str) -> None:
        """Everything but root goes (in chunks), before a full backup is restored."""
        purge(self._unit, root_id)

    def start_restore(self) -> None:
        """Written at once, so a restore that stops halfway leaves the mark."""
        stored_settings.start_restore(self._unit)
        self._unit.flush()

    def restore_unfinished(self) -> bool:
        return stored_settings.restore_unfinished(self._unit)

    def finish_restore(self) -> None:
        stored_settings.finish_restore(self._unit)


class DynamoStorage:
    """The table as storage backend."""

    def __init__(self, table: Table) -> None:
        self.table = table

    @contextmanager
    def transaction(self) -> Iterator[DynamoStore]:
        """Commit when the block succeeds (at most 100 items at once), write nothing when it raises."""
        unit = Unit(self.table)
        yield DynamoStore(unit)
        unit.flush()

    def migrate(self) -> int:
        """Apply pending migrations; a new table starts at the latest version. Refuses a table of a newer app."""
        item = self.table.get(META, SCHEMA)
        version = int(item['version']) if item else LATEST
        if version > LATEST:
            raise SchemaVersionError(f'Table schema {version} is newer than this app ({LATEST})')
        for number in range(version, LATEST):
            MIGRATIONS[number - 1](self.table)
            self._save_version(number + 1)
        if item is None:
            self._save_version(LATEST)
        return LATEST

    def _save_version(self, version: int) -> None:
        unit = Unit(self.table)
        unit.put({'PK': META, 'SK': SCHEMA, 'version': version})
        unit.flush()
