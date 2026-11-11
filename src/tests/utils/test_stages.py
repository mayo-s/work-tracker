import importlib
import secrets

import boto3
import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.dynamodb.storage import DynamoStorage
from src.modules.storage.dynamodb.table import REGION
from src.modules.storage.sqlite import SqliteStorage
from src.utils.stages import Stage, StageError, current_stage, stage_imprint, stage_origin_secret, stage_storage


@pytest.fixture(autouse=True)
def no_stage(monkeypatch):
    """Neither STAGE (e.g. from .env) nor Lambda's variable, unless a test sets them."""
    monkeypatch.delenv('STAGE', raising=False)
    monkeypatch.delenv('AWS_LAMBDA_FUNCTION_NAME', raising=False)
    monkeypatch.delenv('WORK_TRACKER_TABLE', raising=False)
    monkeypatch.delenv('WORK_TRACKER_IMPRINT_PARAMETER', raising=False)
    monkeypatch.delenv('WORK_TRACKER_ORIGIN_SECRET_PARAMETER', raising=False)


@pytest.fixture
def on_lambda(monkeypatch):
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'work-tracker')
    monkeypatch.setenv('WORK_TRACKER_AUTH', 'on')


def test_local_stage_ignores_case_and_uses_the_sqlite_file(monkeypatch, tmp_path):
    monkeypatch.setenv('STAGE', 'local')
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


def test_lambda_uses_the_table_named_like_the_function(monkeypatch, on_lambda, dynamo_table):
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', dynamo_table.name)
    storage = stage_storage()
    assert isinstance(storage, DynamoStorage) and storage.table.name == dynamo_table.name


def test_another_table_can_be_named(monkeypatch, on_lambda, dynamo_table):
    monkeypatch.setenv('WORK_TRACKER_TABLE', dynamo_table.name)
    assert stage_storage().table.name == dynamo_table.name


@pytest.mark.parametrize('override, parameter', [
    (None, '/work-tracker/imprint'), ('/work-tracker-shared/imprint', '/work-tracker-shared/imprint'),
])
def test_lambda_reads_the_imprint_from_its_parameter(monkeypatch, on_lambda, dynamo_table, override, parameter):
    """SSM is simulated by moto like the table."""
    if override:
        monkeypatch.setenv('WORK_TRACKER_IMPRINT_PARAMETER', override)
    imprint = stage_imprint()
    assert (imprint.where, imprint.read()) == (f'the SSM parameter {parameter}', None)  # not created yet
    boto3.client('ssm', region_name=REGION).put_parameter(Name=parameter, Value='{}', Type='SecureString')
    assert imprint.read() == '{}'


def test_locally_the_imprint_is_in_the_environment_and_requests_need_no_origin_secret(monkeypatch):
    monkeypatch.setenv('STAGE', 'Local')
    assert (stage_imprint().where, stage_origin_secret()) == ('$WORK_TRACKER_IMPRINT', None)


def test_the_lambda_app_answers_only_requests_through_the_domain(monkeypatch, on_lambda, dynamo_table):
    """CloudFront sends the secret of the SSM parameter named like the function (SPEC 7.4)."""
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', dynamo_table.name)
    lambda_app = importlib.reload(importlib.import_module('src.lambda_app'))
    client = testing.TestClient(lambda_app.app)
    assert client.simulate_get('/health').status == falcon.HTTP_403  # no secret yet: nothing gets through
    secret = secrets.token_urlsafe(32)
    boto3.client('ssm', region_name=REGION).put_parameter(Name=f'/{dynamo_table.name}/origin-secret', Value=secret,
                                                          Type='SecureString')
    through = {'X-Origin-Verify': secret}
    assert client.simulate_get('/health', headers=through).status == falcon.HTTP_200
    assert client.simulate_get('/api/auth/status', headers=through).json['setup_token'] is True  # creating root needs it
    bypassing = client.simulate_get('/health', headers={'X-Origin-Verify': secret[:-1]})
    assert (bypassing.status, bypassing.json['description']) == (falcon.HTTP_403, 'Open the app at its address')


def test_app_without_database_runs_on_the_local_stage(monkeypatch, tmp_path):
    monkeypatch.setenv('STAGE', 'Local')
    monkeypatch.setenv('WORK_TRACKER_DB', str(tmp_path / 'local.db'))
    create_app()
    assert (tmp_path / 'local.db').is_file()
