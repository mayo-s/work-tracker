"""Restoring the full backup (SPEC 5.9, TASKS.md 9.1i): everything but root goes, then the backup comes in; on both
backends, and from one to the other."""

import pytest

from src.modules.backup.full import make_backup
from src.modules.backup.restore import BackupError, check_backup, restore_backup
from src.modules.storage.database import Database
from src.modules.storage.dynamodb.storage import DynamoStorage
from src.modules.storage.errors import ConflictError
from src.modules.storage.sqlite import SqliteStorage
from src.tests.modules.backup.conftest import NOW, add_everything
from src.tests.users import KLARA, PASSWORD, RAINER


def backup_of(storage):
    with storage.transaction() as store:
        return make_backup(store, NOW)


def restore(storage, backup):
    with storage.transaction() as store:
        root = store.users().get(store.users().root_id())
        check_backup(backup, root)
        return restore_backup(store, backup, root.id)


def comparable(backup):
    """The backup without what a restore renews: the ids of team services; root's account is the current one."""
    data = backup.model_dump(exclude={'made_at'})
    for team in data['teams']:
        for service in team['services']:
            service['id'] = None
    data['users'] = [item for item in data['users'] if item['user']['role'] != 'root']
    return data


def test_restoring_gives_the_same_database_back(storage, people):
    backup = backup_of(storage)
    with storage.transaction() as store:
        store.users().add(RAINER, PASSWORD)  # comes after the backup, and goes
    summary = restore(storage, backup)
    assert (summary.users, summary.teams, summary.entries, summary.audit_entries) == (2, 2, 1, 1)
    assert comparable(backup_of(storage)) == comparable(backup)


def test_restored_users_log_in_with_their_password(storage, people):
    restore(storage, backup_of(storage))
    with storage.transaction() as store:
        assert store.users().check_password(people['hans'], PASSWORD)
        assert store.users().two_factor(people['hans']).secret == 'ABC'


def test_sessions_of_everyone_but_root_end(storage, people):
    with storage.transaction() as store:
        hans, root = store.sessions().start(people['hans'], NOW), store.sessions().start(people['root'], NOW)
    restore(storage, backup_of(storage))
    with storage.transaction() as store:
        assert (store.sessions().user_id(hans, NOW)[0], store.sessions().user_id(root, NOW)[0]) == (None, people['root'])


def test_root_the_app_settings_and_the_used_setup_tokens_stay(storage, people):
    with storage.transaction() as store:
        store.save_theme(people['root'], 'dark')
        store.use_setup_token('hash', NOW)
    restore(storage, backup_of(storage))
    with storage.transaction() as store:
        assert (store.users().root_id(), store.load_theme(people['root'])) == (people['root'], 'dark')
    with storage.transaction() as store:
        with pytest.raises(ConflictError):
            store.use_setup_token('hash', NOW)


def test_from_sqlite_to_dynamodb_with_another_root(tmp_path, dynamo_table):
    sqlite = SqliteStorage(Database(tmp_path / 'source.db'))
    sqlite.migrate()
    with sqlite.transaction() as store:
        klara_id = store.users().add(KLARA, PASSWORD).id
    add_everything(sqlite, klara_id)
    backup = backup_of(sqlite)
    dynamo = DynamoStorage(dynamo_table)
    dynamo.migrate()
    with dynamo.transaction() as store:
        new_root = store.users().add(RAINER.model_copy(update={'role': 'root'}), PASSWORD).id
    restore(dynamo, backup)
    restored = backup_of(dynamo)
    assert comparable(restored) == comparable(backup) | {'audit_log': comparable(restored)['audit_log']}
    assert [(entry.actor_id, entry.action) for entry in restored.audit_log] == [(new_root, 'registration_switched')]
    assert [item.user.username for item in restored.users if item.user.role == 'root'] == ['rainer']  # root stays


def test_a_restore_that_stops_halfway_is_finished_by_restoring_again(storage, people, monkeypatch):
    backup = backup_of(storage)

    def stop(*args, **kwargs):
        raise TimeoutError('Lambda timed out')

    monkeypatch.setattr('src.modules.backup.restore.import_data', stop)
    with pytest.raises(TimeoutError):
        restore(storage, backup)
    with storage.transaction() as store:
        unfinished = store.restore_unfinished()
    assert unfinished is (storage.__class__ is DynamoStorage)  # SQLite rolled it all back
    monkeypatch.undo()
    restore(storage, backup)
    with storage.transaction() as store:
        assert store.restore_unfinished() is False
    assert comparable(backup_of(storage)) == comparable(backup)


def with_change(backup, **changes):
    return backup.model_copy(update=changes)


def test_a_reference_to_someone_the_backup_does_not_hold(storage, people):
    backup = backup_of(storage)
    broken = with_change(backup, memberships=[backup.memberships[0].model_copy(update={'user_id': 'nobody'})])
    with storage.transaction() as store:
        root = store.users().get(people['root'])
    with pytest.raises(BackupError, match='The backup refers to user nobody, which it does not hold'):
        check_backup(broken, root)


def test_a_username_of_the_current_root(storage, people):
    backup = backup_of(storage)
    with storage.transaction() as store:
        root = store.users().get(people['root']).model_copy(update={'username': 'hans'})
    with pytest.raises(BackupError, match="The username hans is in the backup twice, or is root's"):
        check_backup(backup, root)


def test_a_team_service_the_team_does_not_have(storage, people):
    backup = backup_of(storage)
    teams = [item.model_copy(update={'services': []}) for item in backup.teams]
    with storage.transaction() as store:
        root = store.users().get(people['root'])
    with pytest.raises(BackupError, match='hans uses the service API of Platform, which the backup does not hold'):
        check_backup(with_change(backup, teams=teams), root)
