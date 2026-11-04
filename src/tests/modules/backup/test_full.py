"""The full backup (SPEC 5.9, TASKS.md 9.1h): everything of every user and team, on both backends, and its encrypted
file."""

import json

import pytest

from src.lib.encryption import DecryptionError
from src.models.users import TwoFactor
from src.modules.backup.full import backup_file, make_backup, read_backup_file
from src.tests.modules.backup.conftest import NOW

PASSPHRASE = 'a long backup passphrase'


@pytest.fixture
def backup(storage, people):
    with storage.transaction() as store:
        return make_backup(store, NOW)


def test_the_users_with_password_hashes_two_factor_login_and_records(backup):
    users = {item.user.username: item for item in backup.users}
    assert [item.user.username for item in backup.users] == ['klara', 'pascal', 'hans']
    assert all(item.password_hash.startswith('scrypt$') for item in backup.users)
    assert users['hans'].two_factor == TwoFactor(secret='ABC', enabled=True, last_step=7, recovery=['hash'])
    assert (users['pascal'].user.role, users['pascal'].records) == ('root', None)  # root tracks no work
    assert (backup.made_at, backup.registration) == (NOW.replace(microsecond=0), True)
    hans = users['hans'].records
    assert [(entry.ticket_key, entry.duration) for entry in hans.entries] == [('API-7', 90)]
    services = {service.id: service for service in hans.services}
    ticket = hans.tickets[0]
    assert (services[ticket.service_id].short_name, services[ticket.service_id].team) == ('API', 'Platform')
    assert len(hans.history) == 1


def test_the_teams_also_deleted_with_their_services_members_and_logs(backup, people):
    teams = {item.team.name: item for item in backup.teams}
    assert [(service.short_name, service.name) for service in teams['Platform'].services] == [('API', 'public-api')]
    assert (teams['Platform'].team.deleted_at, teams['Billing'].team.deleted_at, teams['Billing'].services) == (
        None, NOW, [])
    assert [(membership.user_id, membership.team_id, membership.joined_on) for membership in backup.memberships] == [
        (people['hans'], people['platform'], NOW.date())]
    assert [invitation.email for invitation in backup.invitations] == ['rainer.zufall@example.com']
    assert [(auditor.team_id, auditor.user_id) for auditor in backup.auditors] == [(people['platform'], people['klara'])]
    assert [(view.member_id, view.period) for view in backup.report_views] == [(people['hans'], '2026-W45')]
    assert [(entry.actor_id, entry.action) for entry in backup.audit_log] == [(people['root'], 'registration_switched')]


def test_the_file_gives_the_backup_back_with_the_passphrase_only(sqlite_backup):
    content = backup_file(sqlite_backup, PASSPHRASE)
    assert read_backup_file(content, PASSPHRASE) == sqlite_backup
    with pytest.raises(DecryptionError):
        read_backup_file(content, 'another long passphrase')


def test_the_file_header_names_the_format_and_nothing_personal(sqlite_backup):
    content = backup_file(sqlite_backup, PASSPHRASE)
    header = json.loads(content.partition(b'\n')[0])
    assert (header['format'], header['version']) == ('work-tracker-backup', 1)
    assert b'hans' not in content and b'scrypt$' not in content


def replace_header(content, **changes):
    head, _, rest = content.partition(b'\n')
    return json.dumps(json.loads(head) | changes).encode() + b'\n' + rest


@pytest.mark.parametrize('changes, message', [
    ({'format': 'work-tracker'}, 'This is no Work Tracker backup'),
    ({'version': 2}, 'The backup has version 2; this Work Tracker reads up to version 1'),
])
def test_another_file_or_a_newer_version_is_refused(sqlite_backup, changes, message):
    content = replace_header(backup_file(sqlite_backup, PASSPHRASE), **changes)
    with pytest.raises(ValueError, match=message):
        read_backup_file(content, PASSPHRASE)
