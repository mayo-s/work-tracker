import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.models.catalog import Service
from src.models.days import Day
from src.models.entries import Entry
from src.models.history import HistoryAction
from src.models.review import FlagReason
from src.models.teams import Team
from src.modules.storage.sqlite import SqliteStore
from src.modules.userdata.export import export_data
from src.tests.users import HANS, PASSWORD, USER

MONDAY = dt.date(2026, 10, 26)
NOW = dt.datetime(2026, 10, 30, 14, 5, 30, 123456)


@pytest.fixture
def store(conn):
    return SqliteStore(conn)


def export(store, user_id=USER):
    return export_data(store, user_id, NOW)


def activity_type_id(store, name, user_id=USER):
    return next(kind.id for kind in store.activity_types(user_id).all() if kind.name == name)


def test_file_header_and_settings(store):
    store.save_theme(USER, 'dark')
    data = export(store)
    assert (data.format, data.version, data.exported_at) == ('work-tracker', 2, NOW.replace(microsecond=0))
    assert (data.settings.balance_start, data.theme) == (dt.date(2024, 6, 1), 'dark')
    assert [year.year for year in data.pto_years] == [2024, 2025, 2026, 2027]
    assert [(schedule.id, schedule.weekly_minutes) for schedule in data.work_schedules] == [('1', 2400)]


def test_references_use_file_ids(store):
    entries = store.entries(USER)
    entries.delete(entries.create(Entry(date=MONDAY, ticket_key='TNG-1', duration=15)).id)  # database ids from 2
    store.activity_types(USER).delete(activity_type_id(store, 'Meeting'))  # activity type ids from 2
    msb = next(service for service in store.services(USER).all() if service.short_name == 'MSB')
    entries.create(Entry(date=MONDAY, ticket_key='TNG-5213', duration=90, description='bookings'))
    store.tickets(USER).set_service('TNG-5213', msb.id)
    entries.create(Entry(date=MONDAY, activity_type_id=activity_type_id(store, 'Travel'), duration=60))
    data = export(store)
    services = {service.short_name: service.id for service in data.services}
    kinds = {kind.name: kind.id for kind in data.activity_types}
    assert sorted(services.values()) == ['1', '2', '3', '4', '5']
    assert kinds == {'Coding': '1', 'Travel': '2', 'Planning': '3', 'Documentation': '4', 'Other': '5'}
    assert next(ticket for ticket in data.tickets if ticket.key == 'TNG-5213').service_id == services['MSB']
    assert [(entry.id, entry.activity_type_id) for entry in data.entries] == [('1', None), ('2', kinds['Travel'])]


def test_deleted_entries_keep_their_history_after_the_entries(store):
    entries = store.entries(USER)
    deleted = entries.create(Entry(date=MONDAY, ticket_key='TNG-1', duration=15))
    entries.create(Entry(date=MONDAY, ticket_key='TNG-2', duration=30))
    entries.delete(deleted.id)
    data = export(store)
    assert [entry.ticket_key for entry in data.entries] == ['TNG-2']
    lines = [(line.id, line.entry_id, line.action) for line in data.history]
    assert lines == [('1', '2', HistoryAction.CREATED), ('2', '1', HistoryAction.CREATED), ('3', '2', HistoryAction.DELETED)]


def test_history_names_activity_types_and_split_entries_by_file_id(store):
    entries = store.entries(USER)
    entries.delete(entries.create(Entry(date=MONDAY, ticket_key='TNG-1', duration=15)).id)
    meeting, travel = activity_type_id(store, 'Meeting'), activity_type_id(store, 'Travel')
    activity = entries.create(Entry(date=MONDAY, activity_type_id=meeting, duration=60))
    entries.update(activity.model_copy(update={'activity_type_id': travel}))
    store.activity_types(USER).delete(meeting)  # no longer in use
    ticket = entries.create(Entry(date=MONDAY, ticket_key='TNG-2', duration=60))
    entries.split(ticket.id, ['TNG-2', 'TNG-3'])
    data = export(store)
    assert [(entry.id, entry.ticket_key) for entry in data.entries] == [('1', None), ('2', 'TNG-2'), ('3', 'TNG-3')]
    updated = next(line for line in data.history if line.action == HistoryAction.UPDATED)
    assert updated.changes['activity_type_id'] == (None, '2')  # Meeting is gone, Travel comes after Coding
    split_off = next(line for line in data.history if line.detail.startswith('Split from'))
    assert (split_off.entry_id, split_off.detail) == ('3', 'Split from entry 2')


def test_review_flags_on_days_and_entries(store):
    store.days(USER).save(Day(date=MONDAY, day_type='work', start=480, end=990))
    store.days(USER).add_flag(MONDAY, FlagReason.WEEKEND_HOURS, 'Sa 2:00')
    entries = store.entries(USER)
    entries.delete(entries.create(Entry(date=MONDAY, ticket_key='TNG-1', duration=15)).id)
    entry = entries.create(Entry(date=MONDAY, ticket_key='TNG-2', duration=15))
    entries.add_flag(entry.id, FlagReason.UNCERTAIN_TICKET, '#2')
    data = export(store)
    assert [day.date for day in data.days] == [MONDAY]
    flags = [(flag.id, flag.date, flag.entry_id, flag.detail) for flag in data.review_flags]
    assert flags == [('1', MONDAY, None, 'Sa 2:00'), ('2', None, '1', '#2')]


def test_team_services_in_use_are_included_with_the_team(store):
    platform = store.teams().add(Team(name='Platform'))
    auth, _ = (store.team_services(platform.id).add(Service(short_name=name)) for name in ('AUTH', 'UNUSED'))
    store.teams().join(USER, platform.id)
    store.tickets(USER).ensure('TNG-7')
    store.tickets(USER).set_service('TNG-7', auth.id)
    data = export(store)
    team_services = [(service.short_name, service.team) for service in data.services if service.team]
    assert team_services == [('AUTH', 'Platform')]
    assert data.tickets[0].service_id == next(service.id for service in data.services if service.short_name == 'AUTH')


def test_records_of_other_users_are_not_exported(store):
    hans = store.users().add(HANS, PASSWORD).id
    store.days(hans).save(Day(date=MONDAY, day_type='pto'))
    store.entries(hans).create(Entry(date=MONDAY, ticket_key='SECRET-1', duration=60))
    data = export(store)
    assert (data.days, data.entries, data.history, data.tickets) == ([], [], [], [])
    assert [entry.ticket_key for entry in export(store, hans).entries] == ['SECRET-1']


def test_download_as_file(database):
    client = testing.TestClient(create_app(database, clock=lambda: NOW))
    result = client.simulate_get('/api/export')
    assert result.headers['content-disposition'] == 'attachment; filename="work-tracker-klara-2026-10-30.json"'
    assert (result.json['format'], result.json['exported_at']) == ('work-tracker', '2026-10-30T14:05:30')


def test_export_needs_a_login(database):
    client = testing.TestClient(create_app(database, auth=True))
    assert client.simulate_get('/api/export').status == falcon.HTTP_401
