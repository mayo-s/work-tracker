import re

from falcon import testing

from src.app import create_app
from src.modules.storage.dynamodb.storage import DynamoStorage
from src.tests.helpers import session
from src.tests.users import HANS, KLARA, PASSWORD

MILLISECONDS = r'\d+\.\d'


def test_a_logged_in_request_reads_the_session_the_user_and_the_restore_flag_for_its_login(dynamo_table):
    """TASKS.md 14.4c: not the users, to count them, nor the setup state; those only matter without a login."""
    storage = DynamoStorage(dynamo_table)
    client = testing.TestClient(create_app(storage=storage, auth=True, timing=True))
    with storage.transaction() as store:
        store.users().add(KLARA, PASSWORD)
        store.users().add(HANS, PASSWORD)
    cookies = session(client.simulate_post('/api/auth/login', json={'login': 'hans', 'password': PASSWORD}))
    timing = client.simulate_get('/api/audits', cookies=cookies).headers['Server-Timing']  # one query of its own
    assert re.fullmatch(f'app;dur={MILLISECONDS}, db;dur={MILLISECONDS};desc="4 calls, 2 items"', timing), timing
