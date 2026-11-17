"""The DynamoDB base: table, transactions (unit of work), id counters, schema version; simulated by moto."""

import datetime as dt

import pytest

from src.modules.storage.dynamodb.__main__ import main
from src.modules.storage.dynamodb.entry_kinds import to_one_kind
from src.modules.storage.dynamodb.filters import both, either, equals, missing, present
from src.modules.storage.dynamodb.keys import META, SCHEMA
from src.modules.storage.dynamodb.storage import LATEST, DynamoStorage
from src.modules.storage.dynamodb.table import TTL_ATTRIBUTE
from src.modules.storage.dynamodb.unit import MAX_ITEMS, Unit
from src.modules.storage.errors import ConflictError, SchemaVersionError, TooManyChangesError
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


def test_a_transaction_reads_each_item_once(dynamo_table, monkeypatch):
    put_all(dynamo_table, day('2026-10-26', note='stored'))
    reads, get_item = [], dynamo_table.client.get_item
    monkeypatch.setattr(dynamo_table.client, 'get_item', lambda **request: reads.append(request) or get_item(**request))
    unit = Unit(dynamo_table)
    assert unit.get(USER, 'DAY#2026-10-26')['note'] == unit.get(USER, 'DAY#2026-10-26')['note'] == 'stored'
    unit.put(day('2026-10-26', note='changed'))
    unit.flush()  # a chunk written: the transaction knows it without reading again
    assert unit.get(USER, 'DAY#2026-10-26')['note'] == 'changed'
    assert len(reads) == 1


def test_a_transaction_reads_each_range_once_also_as_a_part_of_one_read_before(dynamo_table, monkeypatch):
    """TASKS.md 14.4a: e.g. the dashboard asks for the year's entries after all entries."""
    put_all(dynamo_table, day('2026-10-26', note='Monday'), day('2026-10-27', note='Tuesday'), day('2026-11-02', note='next'))
    reads, query = [], dynamo_table.client.query
    monkeypatch.setattr(dynamo_table.client, 'query', lambda **request: reads.append(request) or query(**request))
    unit = Unit(dynamo_table)
    unit.query_prefix(USER, 'DAY#')[0]['note'] = 'changed by its reader only'
    assert [item['note'] for item in unit.query_prefix(USER, 'DAY#')] == ['Monday', 'Tuesday', 'next']
    assert [item['note'] for item in unit.query(USER, 'DAY#2026-10-27', 'DAY#2026-10-31')] == ['Tuesday']
    unit.put(day('2026-10-28', note='written'))
    assert [item['note'] for item in unit.query(USER, 'DAY#2026-10-27', 'DAY#2026-10-31')] == ['Tuesday', 'written']
    assert len(reads) == 1
    unit.flush()  # a chunk written: ranges are read again
    assert [item['note'] for item in unit.query_prefix(USER, 'DAY#')] == ['Monday', 'Tuesday', 'written', 'next']
    assert len(reads) == 2


def test_a_filter_lets_dynamodb_pick_the_items_and_still_shows_the_own_writes(dynamo_table, monkeypatch):
    """TASKS.md 14.4b: e.g. the open days, of a whole history; an item without the attribute counts as one without
    its value."""
    open_days = both(present('start'), missing('end'))
    put_all(dynamo_table, day('2026-10-26', start=480, end=None), day('2026-10-27', start=480), day('2026-10-28', start=None),
            day('2026-10-29', start=480, end=990), day('2026-10-30', start=480, end=None))
    answers, query = [], dynamo_table.client.query
    monkeypatch.setattr(dynamo_table.client, 'query', lambda **request: answers.append(query(**request)) or answers[-1])
    unit = Unit(dynamo_table)
    unit.put(day('2026-10-26', start=480, end=990))  # closed
    unit.put(day('2026-10-29', start=480, end=None))  # opened again
    unit.delete(USER, 'DAY#2026-10-30')
    assert [item['SK'] for item in unit.query_prefix(USER, 'DAY#', open_days)] == ['DAY#2026-10-27', 'DAY#2026-10-29']
    assert [len(answer['Items']) for answer in answers] == [3]  # of the 5 stored
    unit.query_prefix(USER, 'DAY#')
    assert [item['SK'] for item in unit.query_prefix(USER, 'DAY#', open_days)] == ['DAY#2026-10-27', 'DAY#2026-10-29']
    assert len(answers) == 2  # the range is held now: no third read


def test_a_filter_with_two_values_for_one_name_is_refused():
    with pytest.raises(ValueError, match='Two values for one name'):
        either(equals('duration', 0), equals('duration', 15))


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


def test_a_unique_item_deleted_and_written_again_in_one_transaction(dynamo_table):
    put_all(dynamo_table, CLAIM)
    unit = Unit(dynamo_table)
    unit.delete(CLAIM['PK'], CLAIM['SK'])
    unit.put(CLAIM | {'user_id': 'other'}, unique='The username klara is taken')
    unit.flush()
    assert dynamo_table.get(CLAIM['PK'], CLAIM['SK'])['user_id'] == 'other'


def test_a_new_table_gets_the_latest_schema_version(dynamo_table):
    assert DynamoStorage(dynamo_table).migrate() == LATEST
    assert dynamo_table.get(META, SCHEMA)['version'] == LATEST


def former_entry(entry_id, kind, **values):
    return {'PK': USER, 'SK': f'ENTRY#2026-10-26#{entry_id}', 'id': entry_id, 'kind': kind, 'date': '2026-10-26',
            'duration': 60, **values}


def test_version_2_converts_the_entries_to_one_kind(dynamo_table):
    """SPEC 4.6 as in SQLite (test_database.py); a second run changes nothing, as after a run that stopped halfway."""
    put_all(dynamo_table, {'PK': META, 'SK': SCHEMA, 'version': 1}, {'PK': 'USERS', 'SK': USER, 'order': 1},
            {'PK': USER, 'SK': 'ACTIVITY_TYPE#a1', 'id': 'a1', 'name': 'Meeting'},
            {'PK': USER, 'SK': 'ACTIVITY_TYPE_NAME#meeting', 'id': 'a1'},
            former_entry('e1', 'ticket', ticket_key='TNG-1', description='europace', coding=True),
            former_entry('e2', 'ticket', ticket_key='TNG-2', description='Refinement', coding=False),
            former_entry('e3', 'ticket', ticket_key='TNG-2', description='investigation', coding=False),
            former_entry('e4', 'activity', activity_type_id='a1', note='Standup'))
    storage = DynamoStorage(dynamo_table)
    assert storage.migrate() == LATEST
    to_one_kind(dynamo_table)
    with storage.transaction() as store:
        kinds = {kind.id: kind for kind in store.activity_types(USER.removeprefix('USER#')).all()}
        entries = [(entry.id, entry.ticket_key, kinds[entry.activity_type_id].name if entry.activity_type_id else None,
                    entry.description) for entry in store.entries(USER.removeprefix('USER#')).between(
                        dt.date(2026, 10, 26), dt.date(2026, 10, 26))]
    assert entries == [('e1', 'TNG-1', 'Coding', 'europace'), ('e2', 'TNG-2', 'Meeting', 'Refinement'),
                       ('e3', 'TNG-2', None, 'investigation'), ('e4', None, 'Meeting', 'Standup')]
    assert {(kind.name, kind.ticket_required) for kind in kinds.values()} == {('Meeting', False), ('Coding', True)}


def test_version_3_drops_the_review_flags_of_the_former_import(dynamo_table):
    put_all(dynamo_table, {'PK': META, 'SK': SCHEMA, 'version': 2}, {'PK': 'USERS', 'SK': USER, 'order': 1},
            {'PK': USER, 'SK': 'FLAG#f1', 'id': 'f1', 'date': '2025-12-06', 'reason': 'weekend_hours'}, day('2025-12-06'))
    DynamoStorage(dynamo_table).migrate()
    assert (dynamo_table.get(USER, 'FLAG#f1'), dynamo_table.get(USER, 'DAY#2025-12-06') is not None) == (None, True)


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
