"""The setup token (SPEC 7.4): on AWS Lambda the first user (the admin) is created only with it; SSM simulated by moto."""

import secrets

import boto3
import falcon
import pytest
from falcon import testing
from moto import mock_aws

from src.app import create_app
from src.modules.auth.setup_token import DEFAULT_PARAMETER, SetupToken
from src.modules.storage.dynamodb.table import REGION
from src.tests.users import PASSWORD
from src.utils.stages import stage_setup_token

TOKEN = secrets.token_urlsafe(32)
USER = {'username': 'klara', 'email': 'klara.himmel@example.com', 'first_name': 'Klara', 'last_name': 'Himmel',
        'password': PASSWORD}
SETUP = {'balance_start': '2026-11-02', 'schedule': {'weekly_hours': '40:00', 'work_days': ['Mon']}, 'pto_first_year': 5,
         'user': USER}


@pytest.fixture
def ssm(monkeypatch):
    for name in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SECURITY_TOKEN', 'AWS_SESSION_TOKEN'):
        monkeypatch.setenv(name, 'testing')
    monkeypatch.delenv('AWS_PROFILE', raising=False)
    with mock_aws():
        yield boto3.client('ssm', region_name=REGION)


def app_with(fresh_database, ssm, value=TOKEN):
    if value is not None:
        ssm.put_parameter(Name=DEFAULT_PARAMETER, Value=value, Type='SecureString')
    return testing.TestClient(create_app(fresh_database, auth=True, setup_token=SetupToken(ssm)))


def test_the_first_user_with_the_token(fresh_database, ssm):
    app = app_with(fresh_database, ssm)
    assert app.simulate_get('/api/auth/status').json['setup_token'] is True
    assert app.simulate_post('/api/setup', json=SETUP | {'setup_token': TOKEN}).json == {'done': True}
    assert app.simulate_get('/api/auth/status').json['setup_token'] is False  # no longer needed


@pytest.mark.parametrize('token', [None, '', 'guessed', TOKEN[:-1]])
def test_without_the_right_token_no_user_is_created(fresh_database, ssm, token):
    app = app_with(fresh_database, ssm)
    result = app.simulate_post('/api/setup', json=SETUP | {'setup_token': token})
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'The setup token is wrong')
    assert app.simulate_get('/api/auth/status').json['has_users'] is False


def test_guessing_pauses_after_five_tries(fresh_database, ssm):
    app = app_with(fresh_database, ssm)
    for _ in range(5):
        app.simulate_post('/api/setup', json=SETUP | {'setup_token': 'guessed'})
    assert app.simulate_post('/api/setup', json=SETUP | {'setup_token': TOKEN}).status == falcon.HTTP_429


@pytest.mark.parametrize('path, body', [
    ('/api/auth/first-user', USER),
    ('/api/setup/import', {'data': {'format': 'work-tracker', 'version': 1, 'exported_at': '2026-10-30T12:00:00',
                                    'settings': {'balance_start': '2026-11-02'}, 'theme': 'system', 'work_schedules': [],
                                    'pto_years': [], 'services': [], 'activity_types': [], 'tickets': [], 'days': [],
                                    'entries': [], 'history': [], 'review_flags': []}, 'user': USER}),
])
def test_every_way_to_the_first_user_needs_it(fresh_database, ssm, path, body):
    app = app_with(fresh_database, ssm)
    assert app.simulate_post(path, json=body).status == falcon.HTTP_403
    assert app.simulate_post(path, json=body | {'setup_token': TOKEN}).status in (falcon.HTTP_200, falcon.HTTP_201)


@pytest.mark.parametrize('value, message', [
    (None, f'No setup token is configured: create the parameter {DEFAULT_PARAMETER} first'),
    ('too short', f'The setup token in {DEFAULT_PARAMETER} needs at least 32 characters'),
])
def test_without_a_proper_token_in_ssm_nobody_gets_in(fresh_database, ssm, value, message):
    app = app_with(fresh_database, ssm, value)
    result = app.simulate_post('/api/setup', json=SETUP | {'setup_token': value})
    assert (result.status, result.json['description']) == (falcon.HTTP_409, message)


def test_after_the_first_user_the_token_is_not_needed(fresh_database, ssm):
    app = app_with(fresh_database, ssm)
    app.simulate_post('/api/setup', json=SETUP | {'setup_token': TOKEN})
    ssm.delete_parameter(Name=DEFAULT_PARAMETER)  # deleted after the setup, as the README says
    assert app.simulate_post('/api/auth/login', json={'login': 'klara', 'password': PASSWORD}).status == falcon.HTTP_200


def test_the_token_is_only_used_on_lambda(monkeypatch, ssm):
    monkeypatch.setenv('STAGE', 'Local')
    monkeypatch.delenv('AWS_LAMBDA_FUNCTION_NAME', raising=False)
    assert stage_setup_token() is None


def test_on_lambda_the_token_is_named_like_the_function(monkeypatch, ssm):
    monkeypatch.delenv('STAGE', raising=False)
    monkeypatch.delenv('WORK_TRACKER_SETUP_TOKEN_PARAMETER', raising=False)
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'work-tracker-dev')
    ssm.put_parameter(Name='/work-tracker-dev/setup-token', Value=TOKEN, Type='SecureString')
    assert stage_setup_token().matches(TOKEN)


def test_another_parameter_can_be_named(monkeypatch, ssm):
    monkeypatch.delenv('STAGE', raising=False)
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'work-tracker-dev')
    monkeypatch.setenv('WORK_TRACKER_SETUP_TOKEN_PARAMETER', '/other/token')
    ssm.put_parameter(Name='/other/token', Value=TOKEN, Type='SecureString')
    assert stage_setup_token().matches(TOKEN)
