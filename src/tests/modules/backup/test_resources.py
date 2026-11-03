"""The full backup on /api/admin/backup (SPEC 5.9): root downloads it, encrypted with its passphrase."""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.backup.full import read_backup_file
from src.modules.storage.users import UserRepository
from src.tests.users import PASCAL, PASSWORD

NOW = dt.datetime(2026, 11, 3, 9, 0)
PASSPHRASE = 'a long backup passphrase'


@pytest.fixture
def app(database):
    with database.transaction() as conn:
        UserRepository(conn).add(PASCAL.model_copy(update={'role': 'root'}), PASSWORD)
    return testing.TestClient(create_app(database, auth=True, clock=lambda: NOW))


def logged_in(app, name):
    result = app.simulate_post('/api/auth/login', json={'login': name, 'password': PASSWORD})
    return {'wt_session': result.cookies['wt_session'].value}


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
