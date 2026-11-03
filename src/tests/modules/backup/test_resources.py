"""The full backup on /api/admin/backup and its restore on /api/admin/restore (SPEC 5.9), for root."""

import base64
import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.backup.full import read_backup_file
from src.modules.storage.database import Database
from src.modules.storage.sqlite import SqliteStore
from src.modules.storage.users import UserRepository
from src.tests.users import PASCAL, PASSWORD, RAINER

NOW = dt.datetime(2026, 11, 3, 9, 0)
PASSPHRASE = 'a long backup passphrase'


@pytest.fixture
def app(database):
    with database.transaction() as conn:
        UserRepository(conn).add(PASCAL.model_copy(update={'role': 'root'}), PASSWORD)
    return testing.TestClient(create_app(database, auth=True, clock=lambda: NOW))


def login(app, name):
    return app.simulate_post('/api/auth/login', json={'login': name, 'password': PASSWORD})


def logged_in(app, name):
    return {'wt_session': login(app, name).cookies['wt_session'].value}


def download(app, cookies, passphrase=PASSPHRASE):
    return app.simulate_post('/api/admin/backup', cookies=cookies, json={'passphrase': passphrase})


def test_root_downloads_the_whole_database(app):
    result = download(app, logged_in(app, 'pascal'))
    assert result.status == falcon.HTTP_200
    assert result.headers['content-type'] == 'application/octet-stream'
    assert result.headers['content-disposition'] == 'attachment; filename="work-tracker-backup-2026-11-03.wtbackup"'
    backup = read_backup_file(result.content, PASSPHRASE)
    assert [item.user.username for item in backup.users] == ['klara', 'pascal']


def test_the_backup_is_in_the_audit_log(app):
    root = logged_in(app, 'pascal')
    download(app, root)
    assert app.simulate_get('/api/admin/audit', cookies=root).json[0]['action'] == 'backup_made'


def test_only_root(app):
    result = download(app, logged_in(app, 'klara'))
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'Only root may do this')


def test_the_passphrase_needs_12_characters(app):
    assert download(app, logged_in(app, 'pascal'), 'too short').status_code == 422


def restore(app, cookies, content, passphrase=PASSPHRASE, confirm=None):
    return app.simulate_post('/api/admin/restore', cookies=cookies, json={
        'file': base64.b64encode(content).decode(), 'passphrase': passphrase, 'confirm': confirm})


@pytest.fixture
def backup(app):
    return download(app, logged_in(app, 'pascal')).content


def test_restoring_over_other_users_needs_the_purge_confirmed(app, backup):
    root = logged_in(app, 'pascal')
    result = restore(app, root, backup)
    assert (result.status, result.json['code']) == (falcon.HTTP_409, 'purge_required')
    done = restore(app, root, backup, confirm='purge')
    assert done.status == falcon.HTTP_200
    assert done.json == {'users': 1, 'teams': 0, 'entries': 0, 'audit_entries': 0}  # Klara; root stays


def test_other_sessions_end_and_root_stays_logged_in(app, backup):
    klara, root = logged_in(app, 'klara'), logged_in(app, 'pascal')
    restore(app, root, backup, confirm='purge')
    assert app.simulate_get('/api/dashboard', cookies=klara).status == falcon.HTTP_401
    assert app.simulate_get('/api/admin/users', cookies=root).status == falcon.HTTP_200
    log = app.simulate_get('/api/admin/audit', cookies=root).json
    assert [entry['action'] for entry in log] == ['backup_restored']  # the backup holds the log from before it
    assert login(app, 'klara').status == falcon.HTTP_200  # with the password of the backup


def test_with_nobody_but_root_at_once(database, tmp_path):
    fresh = Database(tmp_path / 'fresh.db')
    fresh.migrate()
    with fresh.transaction() as conn:
        UserRepository(conn).add(RAINER.model_copy(update={'role': 'root'}), PASSWORD)
    with database.transaction() as conn:
        UserRepository(conn).add(PASCAL.model_copy(update={'role': 'root'}), PASSWORD)
    source = testing.TestClient(create_app(database, auth=True, clock=lambda: NOW))
    content = download(source, logged_in(source, 'pascal')).content
    target = testing.TestClient(create_app(fresh, auth=True, clock=lambda: NOW))
    assert restore(target, logged_in(target, 'rainer'), content).status == falcon.HTTP_200
    assert login(target, 'klara').status == falcon.HTTP_200


@pytest.mark.parametrize('content, passphrase, message', [
    (None, 'another long passphrase', 'The passphrase is wrong, or the file is damaged'),
    (b'{"format": "work-tracker", "version": 1}\nrest', PASSPHRASE, 'This is no Work Tracker backup'),
    (b'not a backup', PASSPHRASE, 'The file has no header'),
])
def test_a_file_that_cannot_be_read_is_refused_before_anything_changes(app, backup, content, passphrase, message):
    root = logged_in(app, 'pascal')
    result = restore(app, root, content or backup, passphrase, confirm='purge')
    assert (result.status_code, result.json['description']) == (422, message)
    assert len(app.simulate_get('/api/admin/users', cookies=root).json) == 2


def test_only_root_restores(app, backup):
    result = restore(app, logged_in(app, 'klara'), backup, confirm='purge')
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'Only root may do this')


def test_until_an_unfinished_restore_is_done_only_root_uses_the_app(app, database):
    klara = logged_in(app, 'klara')
    with database.transaction() as conn:
        SqliteStore(conn).start_restore()
    assert app.simulate_get('/api/dashboard', cookies=klara).status == falcon.HTTP_503
    refused = login(app, 'klara')
    assert (refused.status, refused.json['description']) == (
        falcon.HTTP_503, 'A restore of the full backup is not finished yet; until then, only root can use the app')
    root = logged_in(app, 'pascal')
    assert app.simulate_get('/api/admin/settings', cookies=root).json['restore_unfinished'] is True
