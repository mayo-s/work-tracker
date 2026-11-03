"""The full backup (SPEC 5.9, TASKS.md 9.1h): everything of every user and team, on both backends, and its encrypted
file."""

import datetime as dt
import json

import pytest

from src.lib.encryption import DecryptionError
from src.models.audit import AuditEntry
from src.models.catalog import Service
from src.models.entries import TicketEntry
from src.models.teams import Auditor, ReportView, Team
from src.models.users import TwoFactor
from src.modules.backup.full import backup_file, make_backup, read_backup_file
from src.tests.users import HANS, PASCAL, PASSWORD

NOW = dt.datetime(2026, 11, 3, 9, 0, 30, 123456)
MONDAY = dt.date(2026, 11, 2)
PASSPHRASE = 'a long backup passphrase'


@pytest.fixture
def people(storage, klara_id):
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
def backup(storage, people):
    with storage.transaction() as store:
        return make_backup(store, NOW)


def test_the_users_with_password_hashes_and_two_factor_login(backup, people):
    users = {item.user.username: item for item in backup.users}
    assert [item.user.username for item in backup.users] == ['klara', 'pascal', 'hans']
    assert all(item.password_hash.startswith('scrypt$') for item in backup.users)
    assert users['hans'].two_factor == TwoFactor(secret='ABC', enabled=True, last_step=7, recovery=['hash'])
    assert (users['pascal'].user.role, users['pascal'].records) == ('root', None)  # root tracks no work
    assert (backup.made_at, backup.registration) == (NOW.replace(microsecond=0), True)


def test_the_records_of_each_user(backup):
    hans = next(item for item in backup.users if item.user.username == 'hans').records
    assert [(entry.ticket_key, entry.duration) for entry in hans.entries] == [('API-7', 90)]
    services = {service.id: service for service in hans.services}
    ticket = hans.tickets[0]
    assert (services[ticket.service_id].short_name, services[ticket.service_id].team) == ('API', 'Platform')
    assert len(hans.history) == 1


def test_the_teams_also_deleted_with_their_services(backup, people):
    teams = {item.team.name: item for item in backup.teams}
    assert [(service.short_name, service.name) for service in teams['Platform'].services] == [('API', 'public-api')]
    assert (teams['Platform'].team.deleted_at, teams['Billing'].team.deleted_at, teams['Billing'].services) == (
        None, NOW, [])


def test_memberships_invitations_auditors_views_and_audit_log(backup, people):
    assert [(membership.user_id, membership.team_id, membership.joined_on) for membership in backup.memberships] == [
        (people['hans'], people['platform'], NOW.date())]
    assert [invitation.email for invitation in backup.invitations] == ['rainer.zufall@example.com']
    assert [(auditor.team_id, auditor.user_id) for auditor in backup.auditors] == [(people['platform'], people['klara'])]
    assert [(view.member_id, view.period) for view in backup.report_views] == [(people['hans'], '2026-W45')]
    assert [(entry.actor_id, entry.action) for entry in backup.audit_log] == [(people['root'], 'registration_switched')]


def test_the_file_gives_the_backup_back_with_the_passphrase(backup):
    assert read_backup_file(backup_file(backup, PASSPHRASE), PASSPHRASE) == backup


def test_the_file_header_names_the_format_and_nothing_personal(backup):
    content = backup_file(backup, PASSPHRASE)
    header = json.loads(content.partition(b'\n')[0])
    assert (header['format'], header['version']) == ('work-tracker-backup', 1)
    assert b'hans' not in content and b'scrypt$' not in content


def test_a_wrong_passphrase_is_refused(backup):
    content = backup_file(backup, PASSPHRASE)
    with pytest.raises(DecryptionError):
        read_backup_file(content, 'another long passphrase')


def replace_header(content, **changes):
    head, _, rest = content.partition(b'\n')
    return json.dumps(json.loads(head) | changes).encode() + b'\n' + rest


@pytest.mark.parametrize('changes, message', [
    ({'format': 'work-tracker'}, 'This is no Work Tracker backup'),
    ({'version': 2}, 'The backup has version 2; this Work Tracker reads up to version 1'),
])
def test_another_file_or_a_newer_version_is_refused(backup, changes, message):
    content = replace_header(backup_file(backup, PASSPHRASE), **changes)
    with pytest.raises(ValueError, match=message):
        read_backup_file(content, PASSPHRASE)
