import pytest

from src.app import create_app
from src.modules.storage.sqlite import SqliteStorage
from src.utils.stages import Stage, StageError, current_stage, stage_storage


@pytest.fixture(autouse=True)
def no_stage(monkeypatch):
    """Neither STAGE (e.g. from .env) nor Lambda's variable, unless a test sets them."""
    monkeypatch.delenv('STAGE', raising=False)
    monkeypatch.delenv('AWS_LAMBDA_FUNCTION_NAME', raising=False)


@pytest.fixture
def on_lambda(monkeypatch):
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'work-tracker')
    monkeypatch.setenv('WORK_TRACKER_AUTH', 'on')


@pytest.mark.parametrize('value', ['Local', 'local', 'LOCAL'])
def test_local_stage(monkeypatch, value):
    monkeypatch.setenv('STAGE', value)
    assert current_stage() is Stage.LOCAL


def test_local_stage_uses_the_sqlite_file(monkeypatch, tmp_path):
    monkeypatch.setenv('STAGE', 'Local')
    monkeypatch.setenv('WORK_TRACKER_DB', str(tmp_path / 'local.db'))
    storage = stage_storage()
    assert isinstance(storage, SqliteStorage)
    assert storage.database.path == str(tmp_path / 'local.db')


def test_missing_stage_stops_with_a_hint():
    with pytest.raises(StageError, match='STAGE is not set: put STAGE=Local into .env'):
        current_stage()


def test_unknown_stage_stops(monkeypatch):
    monkeypatch.setenv('STAGE', 'Production')
    with pytest.raises(StageError, match='Unknown STAGE=Production'):
        current_stage()


def test_lambda_is_detected_without_stage(on_lambda):
    assert current_stage() is Stage.LAMBDA


def test_local_stage_on_lambda_stops(monkeypatch, on_lambda):
    monkeypatch.setenv('STAGE', 'Local')
    with pytest.raises(StageError, match='STAGE=Local on AWS Lambda'):
        current_stage()


def test_login_cannot_be_switched_off_on_lambda(monkeypatch, on_lambda):
    monkeypatch.setenv('WORK_TRACKER_AUTH', 'off')
    with pytest.raises(StageError, match='WORK_TRACKER_AUTH=off is for local development only'):
        stage_storage()


def test_lambda_has_no_storage_yet(on_lambda):
    with pytest.raises(StageError, match='DynamoDB storage'):
        stage_storage()


def test_app_without_database_stops_without_stage():
    with pytest.raises(StageError, match='STAGE is not set'):
        create_app()


def test_app_without_database_runs_on_the_local_stage(monkeypatch, tmp_path):
    monkeypatch.setenv('STAGE', 'Local')
    monkeypatch.setenv('WORK_TRACKER_DB', str(tmp_path / 'local.db'))
    create_app()
    assert (tmp_path / 'local.db').is_file()
