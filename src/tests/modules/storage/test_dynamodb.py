"""The DynamoDB base: table, transactions (unit of work), id counters, schema version; simulated by moto."""

import datetime as dt

import pytest

from src.modules.storage.dynamodb.__main__ import main
from src.modules.storage.dynamodb.keys import META, SCHEMA
from src.modules.storage.dynamodb.storage import LATEST, DynamoStorage
from src.modules.storage.dynamodb.table import TTL_ATTRIBUTE
from src.modules.storage.dynamodb.unit import MAX_ITEMS, Unit
from src.modules.storage.errors import ConflictError, SchemaVersionError, TooManyChangesError
from src.modules.storage.owners import DEFAULT_ACTIVITY_TYPES
from src.modules.storage.users import SESSION_LIFETIME, token_hash
from src.tests.users import KLARA

USER = 'USER#5f0c2a9e'
LOGIN = dt.datetime(2026, 10, 29, 8, 0)


def day(date, **values):
    return {'PK': USER, 'SK': f'DAY#{date}', **values}


def put_all(table, *items):
    unit = Unit(table)
    for item in items:
        unit.put(item)
    unit.flush()


def test_table_is_on_demand_with_time_to_live_and_point_in_time_recovery(dynamo_table):
    client, name = dynamo_table.client, dynamo_table.name
    table = client.describe_table(TableName=name)['Table']
    assert [part['AttributeName'] for part in table['KeySchema']] == ['PK', 'SK']
    assert table['BillingModeSummary']['BillingMode'] == 'PAY_PER_REQUEST'
    assert client.describe_time_to_live(TableName=name)['TimeToLiveDescription'] == {
        'TimeToLiveStatus': 'ENABLED', 'AttributeName': TTL_ATTRIBUTE}
    backups = client.describe_continuous_backups(TableName=name)['ContinuousBackupsDescription']
    assert backups['PointInTimeRecoveryDescription']['PointInTimeRecoveryStatus'] == 'ENABLED'


def test_create_table_command(dynamo_table, capsys):
    main(['create-table', 'work-tracker'])
    assert 'Created work-tracker in eu-central-1' in capsys.readouterr().out
    assert 'work-tracker' in dynamo_table.client.list_tables()['TableNames']


def test_writes_wait_for_the_end_of_the_transaction(dynamo_table):
    unit = Unit(dynamo_table)
    unit.put(day('2026-10-26', note='release'))
    assert dynamo_table.get(USER, 'DAY#2026-10-26') is None
    unit.flush()
    assert dynamo_table.get(USER, 'DAY#2026-10-26')['note'] == 'release'


def test_reads_see_the_own_writes_and_deletes(dynamo_table):
    put_all(dynamo_table, day('2026-10-26', note='stored'), day('2026-10-28', note='stored'))
    unit = Unit(dynamo_table)
    unit.put(day('2026-10-27', note='new'))
    unit.put(day('2026-10-28', note='changed'))
    unit.delete(USER, 'DAY#2026-10-26')
    assert [item['note'] for item in unit.query_prefix(USER, 'DAY#')] == ['new', 'changed']
    assert unit.get(USER, 'DAY#2026-10-26') is None
    assert [item['SK'] for item in unit.query(USER, 'DAY#2026-10-27', 'DAY#2026-10-27')] == ['DAY#2026-10-27']


def test_a_query_reads_every_page(dynamo_table, monkeypatch):
    note = 'x' * 50_000  # 25 items of 50 KB are more than the 1 MB of one page
    for start in range(0, 25, 5):
        put_all(dynamo_table, *(day(f'2026-10-{number:02d}', note=note) for number in range(start + 1, start + 6)))
    pages, query = [], dynamo_table.client.query
    monkeypatch.setattr(dynamo_table.client, 'query', lambda **request: pages.append(request) or query(**request))
    assert len(dynamo_table.query(USER, 'DAY#', 'DAY#~')) == 25
    assert len(pages) == 2


def test_at_most_100_items_are_written_together(dynamo_table):
    unit = Unit(dynamo_table)
    for number in range(MAX_ITEMS + 1):
        unit.put(day(f'2026-{number:03d}'))
    with pytest.raises(TooManyChangesError, match='touches 101 records; at most 100'):
        unit.flush()
    assert dynamo_table.query(USER, 'DAY#', 'DAY#~') == []


def test_a_larger_change_is_written_in_chunks(dynamo_table):
    unit = Unit(dynamo_table)
    for number in range(150):
        unit.put(day(f'2026-{number:03d}'))
        if number % MAX_ITEMS == MAX_ITEMS - 1:
            unit.flush()
    unit.flush()
    assert len(dynamo_table.query(USER, 'DAY#', 'DAY#~')) == 150


CLAIM = {'PK': 'LOGIN', 'SK': 'USERNAME#klara', 'user_id': 'klara'}


def test_a_unique_item_that_exists_is_refused_at_once(dynamo_table):
    put_all(dynamo_table, CLAIM)
    with pytest.raises(ConflictError, match='The username klara is taken'):
        Unit(dynamo_table).put(CLAIM | {'user_id': 'other'}, unique='The username klara is taken')


def test_a_unique_item_written_meanwhile_fails_the_whole_transaction(dynamo_table):
    unit = Unit(dynamo_table)
    unit.put(day('2026-10-26'))
    unit.put(CLAIM | {'user_id': 'other'}, unique='The username klara is taken')
    put_all(dynamo_table, CLAIM)  # another request, between the check and the end of this transaction
    with pytest.raises(ConflictError, match='The username klara is taken'):
        unit.flush()
    assert dynamo_table.get(USER, 'DAY#2026-10-26') is None


def test_ids_count_up_and_are_never_given_twice(dynamo_table):
    assert [dynamo_table.next_id('entry') for _ in range(3)] == [1, 2, 3]
    assert dynamo_table.next_id('service') == 1


def test_a_new_table_gets_the_latest_schema_version(dynamo_table):
    assert DynamoStorage(dynamo_table).migrate() == LATEST
    assert dynamo_table.get(META, SCHEMA)['version'] == LATEST


def test_a_table_of_a_newer_app_is_refused(dynamo_table):
    put_all(dynamo_table, {'PK': META, 'SK': SCHEMA, 'version': LATEST + 1})
    with pytest.raises(SchemaVersionError, match=f'Table schema {LATEST + 1} is newer than this app'):
        DynamoStorage(dynamo_table).migrate()


def test_session_tokens_are_stored_hashed_and_expire(dynamo_table):
    storage = DynamoStorage(dynamo_table)
    with storage.transaction() as store:
        user_id = store.users().add(KLARA, 'correct horse battery 9!').id
        token = store.sessions().start(user_id, LOGIN)
    session = dynamo_table.get(f'SESSION#{token_hash(token)}', 'SESSION')
    assert token not in str(session) and session['expires_at'] == int((LOGIN + SESSION_LIFETIME).timestamp()) + 1


def test_a_new_user_starts_with_the_default_activity_types(dynamo_table):
    with DynamoStorage(dynamo_table).transaction() as store:
        user_id = store.users().add(KLARA, 'correct horse battery 9!').id
    names = [item['name'] for item in dynamo_table.query(f'USER#{user_id}', 'ACTIVITY_TYPE#', 'ACTIVITY_TYPE#~')]
    assert names == list(DEFAULT_ACTIVITY_TYPES)
