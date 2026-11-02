"""The deployment settings (SPEC 7.4): two stages from one shared base, what goes to AWS Lambda, and what must not."""

import importlib.util
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
ZAPPA = json.loads((ROOT / 'zappa_settings.json').read_text())
POLICY = (ROOT / 'deploy' / 'lambda-policy.json').read_text()
STAGES = ['dev', 'prod']


def stage(name):
    """The settings of a stage as zappa reads them: those of the stage it extends, with its own on top."""
    settings = dict(ZAPPA[name])
    return stage(settings.pop('extends')) | settings if 'extends' in settings else settings


def test_dev_and_prod_share_one_base_and_differ_only_in_their_bucket():
    assert set(ZAPPA) == {'base', 'dev', 'prod'}
    for name in STAGES:
        assert ZAPPA[name] == {'extends': 'base', 's3_bucket': f'work-tracker-deploy-{name}'}


def test_no_account_id_in_the_settings_and_the_policy():
    for text in (json.dumps(ZAPPA), POLICY):
        assert not re.search(r'\d{12}', text)


@pytest.mark.parametrize('name', STAGES)
def test_the_app_function_exists(name):
    module, function = stage(name)['app_function'].rsplit('.', 1)
    assert (module, function) == ('src.lambda_app', 'app') and importlib.util.find_spec(module)


@pytest.mark.parametrize('name', STAGES)
def test_requests_and_their_data_are_not_logged(name):
    assert stage(name)['log_level'] == 'WARNING'  # zappa's default, DEBUG, logs every request with cookies and body


@pytest.mark.parametrize('kept_out', ['examples', '*.db', '.env', 'tests', '.venv', 'node_modules'])
def test_private_data_and_tools_stay_out_of_the_package(kept_out):
    assert all(kept_out in stage(name)['exclude'] for name in STAGES)


@pytest.mark.parametrize('name', STAGES)
def test_a_function_url_without_cors_and_without_api_gateway(name):
    settings = stage(name)
    assert (settings['function_url_enabled'], settings['apigateway_enabled'], settings['function_url_config']) == (
        True, False, {'authorizer': 'NONE', 'cors': {}})


@pytest.mark.parametrize('name', STAGES)
def test_each_stage_uses_its_own_role_and_berlin_time(name):
    settings = stage(name)
    assert settings['manage_roles'] is False and 'role_arn' not in settings  # zappa finds work-tracker-<stage>-…Role
    assert settings['aws_environment_variables'] == {'TZ': 'CET-1CEST,M3.5.0,M10.5.0/3'}


def test_the_role_of_a_stage_reaches_only_its_table_its_token_and_its_logs():
    policy = json.loads(POLICY.replace('STAGE', 'dev'))
    resources = [statement['Resource'] for statement in policy['Statement']]
    assert resources == ['arn:aws:dynamodb:eu-central-1:*:table/work-tracker-dev',
                         'arn:aws:ssm:eu-central-1:*:parameter/work-tracker-dev/setup-token', '*',
                         'arn:aws:logs:eu-central-1:*:log-group:/aws/lambda/work-tracker-dev*']
    assert policy['Statement'][2]['Condition'] == {'StringEquals': {'kms:ViaService': 'ssm.eu-central-1.amazonaws.com'}}
