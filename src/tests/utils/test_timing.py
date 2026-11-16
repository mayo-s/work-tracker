import re

from falcon import testing

from src.app import create_app
from src.modules.storage.dynamodb.storage import DynamoStorage
from src.tests.users import KLARA, PASSWORD

MILLISECONDS = r'\d+\.\d'


def test_no_server_timing_unless_switched_on(database, monkeypatch):
    assert 'Server-Timing' not in testing.TestClient(create_app(database)).simulate_get('/health').headers
    monkeypatch.setenv('WORK_TRACKER_TIMING', 'on')
    assert 'Server-Timing' in testing.TestClient(create_app(database)).simulate_get('/health').headers


def test_server_timing_tells_the_time_in_the_app_and_marks_the_first_request_of_the_instance(database):
    client = testing.TestClient(create_app(database, timing=True))
    first, second = client.simulate_get('/health'), client.simulate_get('/no-such-page')
    assert re.fullmatch(f'app;dur={MILLISECONDS}, first;dur={MILLISECONDS};desc="first request of the instance"',
                        first.headers['Server-Timing'])
    assert re.fullmatch(f'app;dur={MILLISECONDS}', second.headers['Server-Timing'])  # also on a refusal (404)


def test_server_timing_counts_the_calls_to_dynamodb_and_the_items_read(dynamo_table):
    storage = DynamoStorage(dynamo_table)
    client = testing.TestClient(create_app(storage=storage, timing=True))
    with storage.transaction() as store:
        store.users().add(KLARA, PASSWORD)  # with her five activity types
    timing = client.simulate_get('/api/activity-types').headers['Server-Timing']
    assert re.fullmatch(f'app;dur={MILLISECONDS}, db;dur={MILLISECONDS};desc="2 calls, 6 items", first;.+', timing), timing
