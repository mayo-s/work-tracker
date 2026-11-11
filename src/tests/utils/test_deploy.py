"""The deployment settings (SPEC 7.4): two stages from one shared base, what goes to AWS Lambda, and what must not."""

import importlib.util
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
ZAPPA = json.loads((ROOT / 'zappa_settings.json').read_text())
POLICY = (ROOT / 'deploy' / 'lambda-policy.json').read_text()
TRUST = (ROOT / 'deploy' / 'lambda-trust-policy.json').read_text()
CLOUDFRONT = (ROOT / 'deploy' / 'cloudfront.json').read_text()
DNS_ALIAS = (ROOT / 'deploy' / 'dns-alias.json').read_text()
STATIC_POLICY = (ROOT / 'deploy' / 'cache-policy-static.json').read_text()
STAGES = ['dev', 'prod']
BASE = ZAPPA['base']  # the stages differ only in their bucket


def test_dev_and_prod_share_one_base_and_differ_only_in_their_bucket():
    assert set(ZAPPA) == {'base', 'dev', 'prod'}
    for name in STAGES:
        assert ZAPPA[name] == {'extends': 'base', 's3_bucket': f'work-tracker-deploy-{name}'}


def test_no_account_id_in_the_settings_and_the_policy():
    for text in (json.dumps(ZAPPA), POLICY, TRUST, CLOUDFRONT, DNS_ALIAS, STATIC_POLICY):
        assert not re.search(r'\d{12}', text)


def test_the_function():
    module, function = BASE['app_function'].rsplit('.', 1)
    assert (module, function) == ('src.lambda_app', 'app') and importlib.util.find_spec(module)
    assert BASE['log_level'] == 'WARNING'  # zappa's default, DEBUG, logs every request with cookies and body
    assert (BASE['function_url_enabled'], BASE['apigateway_enabled'], BASE['function_url_config']) == (
        True, False, {'authorizer': 'NONE', 'cors': {}})  # a function URL without CORS and without API Gateway
    assert BASE['manage_roles'] is False and 'role_arn' not in BASE  # zappa finds work-tracker-<stage>-…Role
    assert BASE['aws_environment_variables'] == {'TZ': 'CET-1CEST,M3.5.0,M10.5.0/3'}  # Berlin time


def test_private_data_tools_and_project_folders_stay_out_of_the_package():
    assert {'*.db', '.env', '.venv', 'node_modules'} <= set(BASE['exclude'])
    assert {'examples', 'docs', 'src/tests', 'src/templates/tests'} <= set(BASE['exclude_glob'])


def test_no_folder_name_that_packages_use_is_excluded_by_name():
    """`exclude` matches names in the installed packages too: `docs` once took botocore.docs, which zappa imports."""
    assert {'docs', 'tests', 'examples', 'data', 'deploy'} & set(BASE['exclude']) == set()


def test_the_role_of_a_stage_reaches_only_its_table_its_parameters_and_its_logs():
    policy = json.loads(POLICY.replace('STAGE', 'dev'))
    resources = [statement['Resource'] for statement in policy['Statement']]
    assert resources == ['arn:aws:dynamodb:eu-central-1:*:table/work-tracker-dev',
                         ['arn:aws:ssm:eu-central-1:*:parameter/work-tracker-dev/setup-token',
                          'arn:aws:ssm:eu-central-1:*:parameter/work-tracker-dev/imprint',
                          'arn:aws:ssm:eu-central-1:*:parameter/work-tracker-dev/origin-secret'], '*',
                         'arn:aws:logs:eu-central-1:*:log-group:/aws/lambda/work-tracker-dev*']
    assert policy['Statement'][2]['Condition'] == {'StringEquals': {'kms:ViaService': 'ssm.eu-central-1.amazonaws.com'}}


def test_only_lambda_and_the_keep_warm_rule_of_the_stage_may_use_the_role():
    trust = json.loads(TRUST.replace('STAGE', 'dev'))
    assert [statement['Principal']['Service'] for statement in trust['Statement']] == [
        'lambda.amazonaws.com', 'events.amazonaws.com']
    assert trust['Statement'][1]['Condition'] == {
        'ArnLike': {'aws:SourceArn': 'arn:aws:events:eu-central-1:*:rule/work-tracker-dev*'}}


def test_cloudfront_passes_every_request_on_uncached_over_https_with_the_origin_secret():
    """The domain in front of the Function URL; the secret is filled in when the distribution is created."""
    config = json.loads(CLOUDFRONT)
    behavior, [origin] = config['DefaultCacheBehavior'], config['Origins']['Items']
    assert (behavior['CachePolicyId'], behavior['OriginRequestPolicyId']) == (
        '4135ea2d-6df8-44a3-9df3-4b5a84be39ad', 'b689b0a8-53d0-40ab-baf2-68738e2966ac')  # AWS's CachingDisabled and
    # AllViewerExceptHostHeader: cookies, query and headers go on, the Function URL gets its own host
    assert (behavior['ViewerProtocolPolicy'], behavior['AllowedMethods']['Quantity']) == ('redirect-to-https', 7)
    assert origin['CustomOriginConfig']['OriginProtocolPolicy'] == 'https-only'
    assert origin['CustomHeaders']['Items'] == [{'HeaderName': 'X-Origin-Verify', 'HeaderValue': 'SECRET'}]


def test_cloudfront_keeps_the_static_files_for_everyone_alike_until_a_deploy_clears_them():
    """TASKS.md L.22: a page runs the Lambda only for its API calls."""
    [behavior] = json.loads(CLOUDFRONT)['CacheBehaviors']['Items']
    assert (behavior['PathPattern'], behavior['CachePolicyId'], behavior['AllowedMethods']['Items'], behavior['Compress']) == (
        '/static/*', 'STATIC_POLICY', ['GET', 'HEAD'], True)
    policy = json.loads(STATIC_POLICY)
    assert (policy['MinTTL'], policy['MaxTTL']) == (31536000, 31536000)  # a year, also despite the app's no-cache
    key = policy['ParametersInCacheKeyAndForwardedToOrigin']
    assert (key['CookiesConfig'], key['HeadersConfig'], key['QueryStringsConfig']) == (
        {'CookieBehavior': 'none'}, {'HeaderBehavior': 'none'}, {'QueryStringBehavior': 'none'})
    assert "create-invalidation --distribution-id \"$distribution\" --paths '/static/*'" in (
        ROOT / 'deploy' / 'zappa.sh').read_text()


def test_an_existing_distribution_gets_the_static_cache_with_everything_else_unchanged():
    spec = importlib.util.spec_from_file_location('static_cache', ROOT / 'deploy' / 'static_cache.py')
    static_cache = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(static_cache)
    current = json.loads(CLOUDFRONT)  # created before L.22, as get-distribution-config returns it
    del current['CacheBehaviors']
    current['DefaultCacheBehavior'] |= {'SmoothStreaming': False, 'FieldLevelEncryptionId': '',
                                        'LambdaFunctionAssociations': {'Quantity': 0}}
    config = static_cache.with_static_cache({'ETag': 'E2QWRUHAPOMQZL', 'DistributionConfig': current}, 'policy-id')
    assert config == current | {'CacheBehaviors': {'Quantity': 1, 'Items': [{
        'PathPattern': '/static/*', 'TargetOriginId': 'function-url', 'ViewerProtocolPolicy': 'redirect-to-https',
        'AllowedMethods': {'Quantity': 2, 'Items': ['GET', 'HEAD'],
                           'CachedMethods': {'Quantity': 2, 'Items': ['GET', 'HEAD']}},
        'CachePolicyId': 'policy-id', 'Compress': True,
        'SmoothStreaming': False, 'FieldLevelEncryptionId': '', 'LambdaFunctionAssociations': {'Quantity': 0}}]}}
