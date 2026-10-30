import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.models.catalog import Service
from src.models.days import Day
from src.models.entries import ActivityEntry, TicketEntry
from src.models.review import FlagReason
from src.models.schedules import Schedule
from src.models.teams import Team
from src.modules.storage.errors import ConflictError
from src.modules.storage.sqlite import SqliteStore
from src.modules.userdata.export import export_data
from src.modules.userdata.importing import import_data
from src.tests.users import HANS, PASSWORD, USER

MONDAY = dt.date(2026, 10, 26)
NOW = dt.datetime(2026, 10, 30, 14, 5)
LATER = dt.datetime(2026, 11, 2, 9, 0)


@pytest.fixture
def store(conn):
    return SqliteStore(conn)


@pytest.fixture
def hans(store):
    """A new user: the default activity types, not set up yet."""
    return store.users().add(HANS, PASSWORD).id


def kind_id(store, name, user_id=USER):
    return next(kind.id for kind in store.activity_types(user_id).all() if kind.name == name)


def record_klaras_work(store):
    """Something of every kind, also what an export renumbers: deleted entries and activity types, a split, flags."""
    store.save_theme(USER, 'dark')
    store.schedules(USER).add(Schedule(valid_from=dt.date(2027, 1, 1), weekly_minutes=1920, work_days=[1, 2, 3, 4]))
    days, entries = store.days(USER), store.entries(USER, clock=lambda: NOW)
    days.save(Day(date=MONDAY, day_type='work', start=480, end=990, note='release'))
    days.add_flag(MONDAY, FlagReason.WEEKEND_HOURS, 'Sa 2:00')
    entries.delete(entries.create(TicketEntry(date=MONDAY, ticket_key='TNG-1', duration=15)).id)
    tool, meeting = kind_id(store, 'Tool Management'), kind_id(store, 'Meeting')
    activity = entries.create(ActivityEntry(date=MONDAY, activity_type_id=tool, duration=60, note='retro'))
    entries.update(activity.model_copy(update={'activity_type_id': meeting}))
    store.activity_types(USER).delete(tool)
    ticket = entries.create(TicketEntry(date=MONDAY, ticket_key='TNG-5213', duration=120, description='bookings'))
    entries.split(ticket.id, ['TNG-5213', 'TNG-5214'])
    entries.add_flag(ticket.id, FlagReason.UNCERTAIN_TICKET, '#5213')
    msb = next(service for service in store.services(USER).all() if service.short_name == 'MSB')
    store.tickets(USER).set_service('TNG-5213', msb.id)


def test_export_import_and_export_again_gives_the_same_file(store, hans):
    record_klaras_work(store)
    exported = export_data(store, USER, NOW)
    summary = import_data(store, hans, exported)
    assert (summary.entries, summary.history, summary.review_flags, summary.services) == (3, 7, 2, 5)
    assert export_data(store, hans, LATER).model_dump(exclude={'exported_at'}) == exported.model_dump(exclude={'exported_at'})


def test_imported_records_belong_to_the_importing_user(store, hans):
    record_klaras_work(store)
    import_data(store, hans, export_data(store, USER, NOW))
    entries = store.entries(hans).between(MONDAY, MONDAY)
    assert [entry.ticket_key for entry in entries if entry.kind == 'ticket'] == ['TNG-5213', 'TNG-5214']
    assert entries[0].activity_type_id == kind_id(store, 'Meeting', hans)
    assert [line.action for line in store.entries(hans).history(entries[1].id)] == ['created', 'split']
    assert store.days(hans).get(MONDAY).note == 'release'
    assert store.load_theme(hans) == 'dark'
    assert len(store.entries(USER).between(MONDAY, MONDAY)) == 3  # Klara's stay as they are


def test_activity_types_of_the_file_replace_the_defaults(store, hans):
    store.activity_types(USER).add(store.activity_types(USER).get(kind_id(store, 'Other')).model_copy(
        update={'id': None, 'name': 'Hackathon'}))
    import_data(store, hans, export_data(store, USER, NOW))
    assert [kind.name for kind in store.activity_types(hans).all()] == [
        kind.name for kind in store.activity_types(USER).all()]


def test_team_services_become_personal_ones(store, hans):
    platform = store.teams().add(Team(name='Platform'))
    auth, mail = (store.team_services(platform.id).add(Service(short_name=name, name=f'{name} team'))
                  for name in ('AUTH', 'MAIL'))
    store.teams().join(USER, platform.id)
    store.services(USER).add(Service(short_name='mail', name='own'))
    tickets = store.tickets(USER)
    for key, service in (('TNG-1', auth), ('TNG-2', mail)):
        tickets.ensure(key)
        tickets.set_service(key, service.id)
    import_data(store, hans, export_data(store, USER, NOW))
    personal = {service.short_name: service for service in store.services(hans).all()}
    assert (personal['AUTH'].name, 'MAIL' in personal) == ('AUTH team', False)  # an own service with the short name
    tickets = store.tickets(hans)
    assert (tickets.get('TNG-1').service_id, tickets.get('TNG-2').service_id) == (personal['AUTH'].id, personal['mail'].id)


def test_import_needs_a_user_without_days_and_entries(store, hans):
    data = export_data(store, USER, NOW)
    store.days(hans).save(Day(date=MONDAY, day_type='pto'))
    with pytest.raises(ConflictError, match='without days and entries'):
        import_data(store, hans, data)


def test_a_file_referring_to_records_it_does_not_hold_is_refused(store, hans):
    store.tickets(USER).ensure('TNG-1')
    data = export_data(store, USER, NOW)
    broken = data.model_copy(update={'tickets': [data.tickets[0].model_copy(update={'service_id': 99})]})
    with pytest.raises(ConflictError, match='refers to service 99'):
        import_data(store, hans, broken)


@pytest.fixture
def klaras_file(database):
    with database.transaction() as conn:
        record_klaras_work(SqliteStore(conn))
        return export_data(SqliteStore(conn), USER, NOW).model_dump(mode='json')


NEW_USER = {'username': 'hans', 'email': 'hans.dampf@example.com', 'first_name': 'Hans', 'last_name': 'Dampf',
            'password': PASSWORD}


def test_setup_of_a_new_database_from_a_file(fresh_database, klaras_file):
    client = testing.TestClient(create_app(fresh_database, auth=True))
    result = client.simulate_post('/api/setup/import', json={'data': klaras_file, 'user': NEW_USER})
    assert (result.status, result.json['entries'], result.json['days']) == (falcon.HTTP_200, 3, 1)
    cookies = {'wt_session': result.cookies['wt_session'].value}
    assert client.simulate_get('/api/setup', cookies=cookies).json == {'done': True}
    week = client.simulate_get('/api/entries', cookies=cookies, params={'week': '2026-W44'}).json
    assert [entry['ticket_key'] for entry in week if entry['kind'] == 'ticket'] == ['TNG-5213', 'TNG-5214']


def test_a_failed_import_leaves_nothing_behind(fresh_database, klaras_file):
    client = testing.TestClient(create_app(fresh_database, auth=True))
    broken = klaras_file | {'tickets': [{'key': 'TNG-1', 'service_id': 99}]}
    result = client.simulate_post('/api/setup/import', json={'data': broken, 'user': NEW_USER})
    assert result.status == falcon.HTTP_409
    assert result.json['description'] == 'The file refers to service 99, which it does not hold'
    assert client.simulate_get('/api/auth/status').json['has_users'] is False


@pytest.mark.parametrize('change, message', [
    ({'format': 'spreadsheet'}, 'This is no Work Tracker export file'),
    ({'version': 2}, 'The file has version 2; this Work Tracker reads up to version 1'),
])
def test_other_formats_and_newer_versions_are_refused(fresh_database, klaras_file, change, message):
    client = testing.TestClient(create_app(fresh_database, auth=True))
    result = client.simulate_post('/api/setup/import', json={'data': klaras_file | change, 'user': NEW_USER})
    assert result.status_code == 422
    assert message in result.text


def test_a_set_up_user_cannot_import(client, klaras_file):
    result = client.simulate_post('/api/setup/import', json={'data': klaras_file})
    assert (result.status, result.json['description']) == (falcon.HTTP_409, 'Already set up; change the settings on /settings')
