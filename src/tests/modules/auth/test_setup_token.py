"""The setup token (SPEC 7.4): on AWS Lambda root is created only with it; SSM simulated by moto."""

import secrets

import boto3
import falcon
import pytest
from falcon import testing
from moto import mock_aws

from src.app import create_app
from src.modules.auth.setup_token import DEFAULT_PARAMETER, SetupToken
from src.modules.storage.dynamodb.table import REGION
from src.modules.storage.errors import USED_TOKEN
from src.tests.users import PASSWORD
from src.utils.stages import stage_setup_token

TOKEN = secrets.token_urlsafe(32)
ROOT = {'username': 'rainer', 'email': 'rainer.zufall@example.com', 'first_name': 'Rainer', 'last_name': 'Zufall',
        'password': PASSWORD}


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


def create_root(app, token):
    return app.simulate_post('/api/auth/root', json=ROOT | {'setup_token': token})


def test_root_with_the_token(fresh_database, ssm):
    app = app_with(fresh_database, ssm)
    assert app.simulate_get('/api/auth/status').json['setup_token'] is True
    assert create_root(app, TOKEN).status == falcon.HTTP_201
    assert app.simulate_get('/api/auth/status').json['setup_token'] is False  # no longer needed


@pytest.mark.parametrize('token', [None, TOKEN[:-1]])
def test_without_the_right_token_no_root_is_created(fresh_database, ssm, token):
    app = app_with(fresh_database, ssm)
    result = create_root(app, token)
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'The setup token is wrong')
    assert app.simulate_get('/api/auth/status').json['has_root'] is False


def test_guessing_pauses_after_five_tries(fresh_database, ssm):
    app = app_with(fresh_database, ssm)
    for _ in range(5):
        create_root(app, 'guessed')
    assert create_root(app, TOKEN).status == falcon.HTTP_429


def test_a_database_with_users_but_no_root_needs_it_too(database, ssm):
    app = app_with(database, ssm)  # Klara's, from before root existed
    status = app.simulate_get('/api/auth/status').json
    assert (status['has_users'], status['has_root'], status['setup_token']) == (True, False, True)
    assert create_root(app, None).status == falcon.HTTP_403
    assert create_root(app, TOKEN).status == falcon.HTTP_201


@pytest.mark.parametrize('value, message', [
    (None, f'No setup token is configured: create the parameter {DEFAULT_PARAMETER} first'),
    ('too short', f'The setup token in {DEFAULT_PARAMETER} needs at least 32 characters'),
])
def test_without_a_proper_token_in_ssm_nobody_gets_in(fresh_database, ssm, value, message):
    app = app_with(fresh_database, ssm, value)
    result = create_root(app, value)
    assert (result.status, result.json['description']) == (falcon.HTTP_409, message)


def test_after_root_the_token_is_not_needed(fresh_database, ssm):
    app = app_with(fresh_database, ssm)
    create_root(app, TOKEN)
    ssm.delete_parameter(Name=DEFAULT_PARAMETER)  # deleted after the setup, as the README says
    assert app.simulate_post('/api/auth/login', json={'login': 'rainer', 'password': PASSWORD}).status == falcon.HTTP_200


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


def test_a_token_works_once(fresh_database, ssm):
    app = app_with(fresh_database, ssm)
    create_root(app, TOKEN)
    result = reset_root(app, TOKEN)  # the same token again
    assert (result.status, result.json['description']) == (falcon.HTTP_409, USED_TOKEN)


def reset_root(app, token, password='a new root password 8%'):
    return app.simulate_post('/api/auth/root/reset', json={'setup_token': token, 'new_password': password})


def test_root_login_is_reset_with_a_new_token(fresh_database, ssm):
    app = app_with(fresh_database, ssm)
    old_session = {'wt_session': create_root(app, TOKEN).cookies['wt_session'].value}
    new_token = secrets.token_urlsafe(32)
    ssm.put_parameter(Name=DEFAULT_PARAMETER, Value=new_token, Type='SecureString', Overwrite=True)
    assert app.simulate_get('/api/auth/status').json['root_reset'] is True
    result = reset_root(app, new_token)
    assert (result.status, result.json['role']) == (falcon.HTTP_200, 'root')
    assert app.simulate_get('/api/auth/me', cookies=old_session).status == falcon.HTTP_401  # its sessions ended
    login = {'login': 'rainer', 'password': 'a new root password 8%'}
    assert app.simulate_post('/api/auth/login', json=login).status == falcon.HTTP_200
    log = app.simulate_get('/api/admin/audit', cookies={'wt_session': result.cookies['wt_session'].value}).json
    assert [entry['action'] for entry in log] == ['root_login_reset', 'root_created']


def test_a_wrong_token_resets_nothing(fresh_database, ssm):
    app = app_with(fresh_database, ssm)
    create_root(app, TOKEN)
    result = reset_root(app, TOKEN[:-1])
    assert (result.status, result.json['description']) == (falcon.HTTP_403, 'The setup token is wrong')


def test_reset_needs_root_and_a_new_password_by_the_rules(fresh_database, ssm):
    app = app_with(fresh_database, ssm)
    result = reset_root(app, TOKEN)
    assert (result.status, result.json['description']) == (falcon.HTTP_409, 'There is no root yet; create it first')
    create_root(app, secrets.token_urlsafe(32))  # another token, so TOKEN would still be new
    assert reset_root(app, TOKEN, password='too short').status_code == 422


def test_locally_root_login_is_not_reset_this_way(database):
    app = testing.TestClient(create_app(database, auth=True))
    result = reset_root(app, TOKEN)
    assert (result.status, result.json['description']) == (
        falcon.HTTP_409, 'No setup token here; locally, reset the password with the set-password command')
