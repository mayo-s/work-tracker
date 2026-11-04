"""A database with something of everything for the full backup, on both backends."""

import datetime as dt

import pytest

from src.models.audit import AuditEntry
from src.models.catalog import Service
from src.models.entries import TicketEntry
from src.models.teams import Auditor, ReportView, Team
from src.models.users import TwoFactor
from src.modules.backup.full import make_backup
from src.modules.storage.database import Database
from src.modules.storage.sqlite import SqliteStorage
from src.tests.users import HANS, KLARA, PASCAL, PASSWORD

NOW = dt.datetime(2026, 11, 3, 9, 0, 30, 123456)
MONDAY = dt.date(2026, 11, 2)


def add_everything(storage, klara_id):
    """Root Pascal; Klara, an admin and auditor of Platform; Hans in Platform with two-factor login and a ticket of
    the team's service; a deleted team, an open invitation, a report view and an audit entry."""
    with storage.transaction() as store:
        users, teams = store.users(), store.teams(lambda: NOW)
        root = users.add(PASCAL.model_copy(update={'role': 'root'}), PASSWORD).id
        hans = users.add(HANS, PASSWORD).id
        users.save_two_factor(hans, TwoFactor(secret='ABC', enabled=True, last_step=7, recovery=['hash']))
        platform, billing = teams.add(Team(name='Platform')), teams.add(Team(name='Billing'))
        service = store.team_services(platform.id).add(Service(short_name='API', name='public-api'))
        teams.join(hans, platform.id)
        teams.delete(billing.id)
        store.entries(hans).create(TicketEntry(date=MONDAY, ticket_key='API-7', duration=90))
        store.tickets(hans).set_service('API-7', service.id)
        store.invitations(lambda: NOW).invite(platform.id, 'rainer.zufall@example.com', klara_id)
        store.auditors().assign(Auditor(team_id=platform.id, user_id=klara_id, assigned_by=klara_id, assigned_at=NOW))
        store.report_views().add(ReportView(member_id=hans, viewer_id=klara_id, report='week', period='2026-W45',
                                            viewed_at=NOW))
        store.audit_log().add(AuditEntry(actor_id=root, action='registration_switched', detail='on', at=NOW))
        store.set_registration(True)
    return {'klara': klara_id, 'root': root, 'hans': hans, 'platform': platform.id, 'billing': billing.id}


@pytest.fixture
def people(storage, klara_id):
    return add_everything(storage, klara_id)


@pytest.fixture
def sqlite_backup(tmp_path):
    """The backup of such a database on SQLite, for what does not depend on the backend (the file, the checks)."""
    storage = SqliteStorage(Database(tmp_path / 'source.db'))
    storage.migrate()
    with storage.transaction() as store:
        klara_id = store.users().add(KLARA, PASSWORD).id
    add_everything(storage, klara_id)
    with storage.transaction() as store:
        return make_backup(store, NOW)
