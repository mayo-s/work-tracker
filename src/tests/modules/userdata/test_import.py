"""The import of an export file: on SQLite all or nothing, on DynamoDB (moto) in atomic chunks; the HTTP tests run on
SQLite."""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.models.catalog import Service
from src.models.days import Day
from src.models.entries import Entry
from src.models.history import HistoryAction
from src.models.schedules import Schedule
from src.models.teams import Team
from src.modules.storage.dynamodb.storage import DynamoStorage
from src.modules.storage.errors import ConflictError
from src.modules.storage.sqlite import SqliteStore
from src.modules.userdata import importing
from src.modules.userdata.export import export_data
from src.modules.userdata.importing import import_data
from src.tests.helpers import session
from src.tests.users import HANS, PASSWORD, USER

MONDAY = dt.date(2026, 10, 26)
NOW = dt.datetime(2026, 10, 30, 14, 5)
LATER = dt.datetime(2026, 11, 2, 9, 0)


@pytest.fixture
def store(storage, klara_id, service_ids):
    """One transaction on each backend; Klara has her original services."""
    with storage.transaction() as store:
        yield store


@pytest.fixture
def hans(store):
    """A new user: the default activity types, not set up yet."""
    return store.users().add(HANS, PASSWORD).id


def kind_id(store, name, user_id):
    return next(kind.id for kind in store.activity_types(user_id).all() if kind.name == name)


def record_klaras_work(store, klara):
    """Something of every kind, also what an export renumbers: deleted entries and activity types, a split."""
    store.save_theme(klara, 'dark')
    store.save_language(klara, 'es')
    store.save_settings(klara, store.load_settings(klara).model_copy(update={'work_mode': 'tickets'}))
    store.schedules(klara).add(Schedule(valid_from=dt.date(2027, 1, 1), weekly_minutes=1920, work_days=[1, 2, 3, 4]))
    days, entries = store.days(klara), store.entries(klara, clock=lambda: NOW)
    days.save(Day(date=MONDAY, day_type='work', start=480, end=990, note='release'))
    entries.delete(entries.create(Entry(date=MONDAY, ticket_key='TNG-1', duration=15)).id)
    planning, meeting = kind_id(store, 'Planning', klara), kind_id(store, 'Meeting', klara)
    activity = entries.create(Entry(date=MONDAY, activity_type_id=planning, duration=60, description='retro'))
    entries.update(activity.model_copy(update={'activity_type_id': meeting}))
    store.activity_types(klara).delete(planning)
    ticket = entries.create(Entry(date=MONDAY, ticket_key='TNG-5213', duration=60, description='bookings'))
    split_off = entries.create(Entry(date=MONDAY, ticket_key='TNG-5214', duration=60, description='bookings'))
    entries.add_history(split_off.id, HistoryAction.SPLIT, {}, f'Split from entry {ticket.id}')  # recorded before L.12
    msb = next(service for service in store.services(klara).all() if service.short_name == 'MSB')
    store.tickets(klara).set_service('TNG-5213', msb.id)


def test_export_import_and_export_again_gives_the_same_file(store, hans, klara_id):
    record_klaras_work(store, klara_id)
    exported = export_data(store, klara_id, NOW)
    summary = import_data(store, hans, exported)
    assert (summary.entries, summary.history, summary.services) == (3, 7, 5)
    assert export_data(store, hans, LATER).model_dump(exclude={'exported_at'}) == exported.model_dump(exclude={'exported_at'})
    assert len(store.entries(klara_id).between(MONDAY, MONDAY)) == 3  # Klara's stay as they are


def test_activity_types_of_the_file_replace_the_defaults(store, hans, klara_id):
    store.activity_types(klara_id).add(store.activity_types(klara_id).get(kind_id(store, 'Other', klara_id)).model_copy(
        update={'id': None, 'name': 'Hackathon'}))
    import_data(store, hans, export_data(store, klara_id, NOW))
    assert [kind.name for kind in store.activity_types(hans).all()] == [
        kind.name for kind in store.activity_types(klara_id).all()]


def test_team_services_become_personal_ones(store, hans, klara_id):
    platform = store.teams().add(Team(name='Platform'))
    auth, mail = (store.team_services(platform.id).add(Service(short_name=name, name=f'{name} team'))
                  for name in ('AUTH', 'MAIL'))
    store.teams().join(klara_id, platform.id)
    store.services(klara_id).add(Service(short_name='mail', name='own'))
    tickets = store.tickets(klara_id)
    for key, service in (('TNG-1', auth), ('TNG-2', mail)):
        tickets.ensure(key)
        tickets.set_service(key, service.id)
    import_data(store, hans, export_data(store, klara_id, NOW))
    personal = {service.short_name: service for service in store.services(hans).all()}
    assert (personal['AUTH'].name, 'MAIL' in personal) == ('AUTH team', False)  # an own service with the short name
    tickets = store.tickets(hans)
    assert (tickets.get('TNG-1').service_id, tickets.get('TNG-2').service_id) == (personal['AUTH'].id, personal['mail'].id)


def test_import_needs_a_user_without_days_and_entries(store, hans, klara_id):
    data = export_data(store, klara_id, NOW)
    store.days(hans).save(Day(date=MONDAY, day_type='pto'))
    with pytest.raises(ConflictError, match='without days and entries'):
        import_data(store, hans, data)


def add_entries(storage, user_id, count):
    """Klara's entries, in transactions of a few at a time (one DynamoDB transaction holds at most 100 items)."""
    for start in range(0, count, 20):
        with storage.transaction() as store:
            entries = store.entries(user_id, clock=lambda: NOW)
            for number in range(start, min(start + 20, count)):
                day = MONDAY - dt.timedelta(days=number)
                entries.create(Entry(date=day, ticket_key=f'TNG-{number + 1}', duration=60))


def import_file(storage, user_id, data):
    with storage.transaction() as store:
        return import_data(store, user_id, data)


@pytest.fixture
def large_file(storage, klara_id, service_ids):
    """40 entries with their history and tickets: about 160 items, more than one DynamoDB transaction holds."""
    add_entries(storage, klara_id, 40)
    with storage.transaction() as store:
        return export_data(store, klara_id, NOW)


@pytest.fixture
def new_user(storage, klara_id):
    with storage.transaction() as store:
        return store.users().add(HANS, PASSWORD).id


def test_a_large_import(storage, large_file, new_user):
    summary = import_file(storage, new_user, large_file)
    assert (summary.entries, summary.history, summary.tickets) == (40, 40, 40)
    with storage.transaction() as store:
        assert export_data(store, new_user, LATER).model_dump(exclude={'exported_at'}) == large_file.model_dump(
            exclude={'exported_at'})


def stop_at_the_history(monkeypatch):
    def stop(self):
        raise RuntimeError('the connection is gone')
    monkeypatch.setattr(importing._Import, '_history', stop)


def test_an_import_that_stopped_halfway_is_replaced_by_the_next(storage, large_file, new_user, monkeypatch):
    stop_at_the_history(monkeypatch)
    with pytest.raises(RuntimeError, match='the connection is gone'):
        import_file(storage, new_user, large_file)
    with storage.transaction() as store:  # SQLite wrote nothing; DynamoDB wrote chunks and marked the account
        written = store.entries(new_user).between(dt.date.min, dt.date.max)
        assert store.import_unfinished(new_user) == bool(written) == isinstance(storage, DynamoStorage)
    monkeypatch.undo()
    assert import_file(storage, new_user, large_file).entries == 40
    with storage.transaction() as store:
        assert len(store.entries(new_user).between(dt.date.min, dt.date.max)) == 40  # none twice
        assert store.import_unfinished(new_user)  # until the setup is done
        store.finish_setup(new_user)
    with storage.transaction() as store:
        assert (store.import_unfinished(new_user), store.setup_done(new_user)) == (False, True)


def test_a_broken_file_writes_nothing(storage, large_file, new_user):
    broken = large_file.model_copy(update={'tickets': [large_file.tickets[0].model_copy(update={'service_id': '99'})]})
    with pytest.raises(ConflictError, match='refers to service 99'):
        import_file(storage, new_user, broken)
    with storage.transaction() as store:
        assert store.entries(new_user).between(dt.date.min, dt.date.max) == []
        assert not store.import_unfinished(new_user)


@pytest.fixture
def klaras_file(database):
    with database.transaction() as conn:
        record_klaras_work(SqliteStore(conn), USER)
        return export_data(SqliteStore(conn), USER, NOW).model_dump(mode='json')


ROOT = {'username': 'rainer', 'email': 'rainer.zufall@example.com', 'first_name': 'Rainer', 'last_name': 'Zufall',
        'password': PASSWORD}
NEW_USER = {'username': 'hans', 'email': 'hans.dampf@example.com', 'first_name': 'Hans', 'last_name': 'Dampf',
            'password': PASSWORD}


@pytest.fixture
def new_database(fresh_database):
    """A new database run by root, Rainer, where Hans has just registered (logged in, not set up)."""
    client = testing.TestClient(create_app(fresh_database, auth=True))
    root = session(client.simulate_post('/api/auth/root', json=ROOT))
    client.simulate_put('/api/admin/settings', cookies=root, json={'registration': True})
    hans = session(client.simulate_post('/api/auth/register', json=NEW_USER))
    return client, hans


def test_setup_of_a_new_user_from_a_file(new_database, klaras_file):
    client, hans = new_database
    result = client.simulate_post('/api/setup/import', cookies=hans, json={'data': klaras_file})
    assert (result.status, result.json['entries'], result.json['days']) == (falcon.HTTP_200, 3, 1)
    assert client.simulate_get('/api/setup', cookies=hans).json == {'done': True}
    week = client.simulate_get('/api/entries', cookies=hans, params={'week': '2026-W44'}).json
    assert [entry['ticket_key'] for entry in week if entry['ticket_key']] == ['TNG-5213', 'TNG-5214']


@pytest.mark.parametrize('work_mode', [{}, {'work_mode': 'developer'}])  # none (version 1), the former "Developer"
def test_a_file_without_the_way_of_working_or_with_developer_gives_tickets(new_database, klaras_file, work_mode):
    client, hans = new_database
    settings = {key: value for key, value in klaras_file['settings'].items() if key != 'work_mode'} | work_mode
    client.simulate_post('/api/setup/import', cookies=hans, json={'data': klaras_file | {'settings': settings}})
    assert client.simulate_get('/api/settings', cookies=hans).json['work_mode'] == 'tickets'


def test_a_failed_import_leaves_nothing_behind(new_database, klaras_file):
    client, hans = new_database
    broken = klaras_file | {'tickets': [{'key': 'TNG-1', 'service_id': 99}]}
    result = client.simulate_post('/api/setup/import', cookies=hans, json={'data': broken})
    assert result.status == falcon.HTTP_409
    assert result.json['description'] == 'The file refers to service 99, which it does not hold'
    assert client.simulate_get('/api/tickets', cookies=hans).json == []


@pytest.mark.parametrize('change, message', [
    ({'format': 'spreadsheet'}, 'This is no Work Tracker export file'),
    ({'version': 4}, 'The file has version 4; this Work Tracker reads up to version 3'),
])
def test_other_formats_and_newer_versions_are_refused(new_database, klaras_file, change, message):
    client, hans = new_database
    result = client.simulate_post('/api/setup/import', cookies=hans, json={'data': klaras_file | change})
    assert result.status_code == 422
    assert message in result.text


def test_a_file_of_version_1_gets_entries_of_one_kind(new_database, klaras_file):
    """Ticket and activity entries as converted in SPEC 4.6: a PR review becomes Coding, which the file gets."""
    client, hans = new_database
    meeting = next(kind['id'] for kind in klaras_file['activity_types'] if kind['name'] == 'Meeting')
    entries = [
        {'id': '1', 'kind': 'ticket', 'date': '2026-10-26', 'ticket_key': 'TNG-1', 'duration': 60, 'description': 'PR review',
         'coding': False},
        {'id': '2', 'kind': 'activity', 'date': '2026-10-26', 'activity_type_id': meeting, 'duration': 30, 'note': 'Standup'},
    ]
    version_1 = klaras_file | {'version': 1, 'entries': entries, 'history': [], 'review_flags': []}
    assert client.simulate_post('/api/setup/import', cookies=hans, json={'data': version_1}).status == falcon.HTTP_200
    week = client.simulate_get('/api/entries', cookies=hans, params={'week': '2026-W44'}).json
    assert [(entry['activity_type'], entry['ticket_required'], entry['description']) for entry in week] == [
        ('Coding', True, 'PR review'), ('Meeting', False, 'Standup')]


def test_the_review_flags_of_a_file_of_version_2_are_left_out(new_database, klaras_file):
    client, hans = new_database
    flags = [{'id': '1', 'entry_id': klaras_file['entries'][0]['id'], 'date': None, 'reason': 'uncertain_ticket',
              'detail': '#5213'}]
    version_2 = klaras_file | {'version': 2, 'review_flags': flags}
    result = client.simulate_post('/api/setup/import', cookies=hans, json={'data': version_2})
    assert (result.status, result.json['entries']) == (falcon.HTTP_200, 3)


def test_a_set_up_user_cannot_import(client, klaras_file):
    result = client.simulate_post('/api/setup/import', json={'data': klaras_file})
    assert (result.status, result.json['description']) == (falcon.HTTP_409, 'Already set up; change the settings on /settings')
