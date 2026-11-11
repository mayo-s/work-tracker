"""Deleting an account (SPEC 5.7, GDPR Art. 17) on both backends: everything of theirs goes; in other people's records
they stay as "Deleted user" without a name."""

import datetime as dt

import pytest

from src.models.audit import AuditEntry
from src.models.teams import Team
from src.modules.admin.deletion import delete_account
from src.modules.backup.full import make_backup
from src.modules.backup.restore import check_backup
from src.modules.teams.resources import my_team
from src.tests.helpers import run
from src.tests.modules.backup.conftest import MONDAY, NOW, add_everything
from src.tests.users import HANS, PASSWORD, RAINER

LATER = NOW + dt.timedelta(hours=1)


@pytest.fixture
def people(storage, klara_id):
    """add_everything (backup/conftest.py), and an audit entry by Klara about Hans and one by root about Klara."""
    people = add_everything(storage, klara_id)
    with storage.transaction() as store:
        log = store.audit_log()
        log.add(AuditEntry(actor_id=klara_id, action='deactivated', user_id=people['hans'], at=NOW))
        log.add(AuditEntry(actor_id=people['root'], action='support_switched', user_id=klara_id, detail='on', at=NOW))
    return people


def delete(storage, user_id, actor_id):
    run(storage, lambda store: delete_account(store, user_id, actor_id, LATER))


def test_a_deleted_member_goes_with_everything_of_theirs(storage, people):
    hans, klara = people['hans'], people['klara']
    token = run(storage, lambda store: store.sessions().start(hans, NOW))
    with storage.transaction() as store:
        ops = store.teams().add(Team(name='Ops'))
        store.invitations(lambda: NOW).invite(ops.id, 'Hans.Dampf@example.com', klara)
    delete(storage, hans, klara)
    with storage.transaction() as store:
        assert [user.username for user in store.users().all()] == ['klara', 'pascal']
        assert store.sessions().user_id(token, NOW)[0] is None
        assert (store.entries(hans).between(MONDAY, MONDAY), store.tickets(hans).all()) == ([], [])
        assert (store.teams().members(people['platform']), store.teams().stays(people['platform'])) == ([], [])
        assert [invitation.email for invitation in store.invitations().all()] == ['rainer.zufall@example.com']
        assert store.report_views().all() == []
        message = next(message for message in store.messages().all() if message.subject == 'Export')
        assert (message.user_id, message.anonymized) == (None, True)
        assert [(entry.actor_name, entry.action, entry.user_name, entry.detail) for entry in store.audit_log().all()] == [
            ('Pascal Turbo', 'registration_switched', '', 'on'),
            ('Pascal Turbo', 'support_switched', 'Klara Himmel', 'on'),
            ('Klara Himmel', 'account_deleted', '', '')]
        assert store.users().add(HANS, PASSWORD).username == 'hans'  # username and e-mail address are free again


def test_in_other_peoples_records_a_deleted_account_is_deleted_user(storage, people):
    hans, klara, root = people['hans'], people['klara'], people['root']
    rainer = run(storage, lambda store: store.users().add(RAINER, PASSWORD).id)
    delete(storage, klara, klara)
    with storage.transaction() as store:
        assert store.auditors().all() == []
        assert [view.viewer_name for view in store.report_views().of_member(hans)] == ['Deleted user']
        assert [invitation.invited_by for invitation in my_team(store, rainer, MONDAY).invitations] == ['Deleted user']
        message = next(message for message in store.messages().all() if message.subject == 'Export')
        assert (message.user_id, message.anonymized) == (hans, False)
        assert [change.actor_name for change in store.messages().changes(message.id)] == ['Support', 'Support']
        assert [(entry.actor_name, entry.action, entry.user_name, entry.detail) for entry in store.audit_log().all()] == [
            ('Pascal Turbo', 'registration_switched', '', 'on'),
            ('Deleted user', 'deactivated', 'Hans Dampf', ''),
            ('Deleted user', 'account_deleted', '', 'own')]
        check_backup(make_backup(store, LATER), store.users().get(root))  # a backup still holds together
