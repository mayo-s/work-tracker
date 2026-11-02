"""Auditors (SPEC 5.7, TASKS.md 9.1e): an admin assigns a user to teams; they see the team view of everyone who was ever
in them, for the days of each stay, read-only, until the assignment ends."""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.models.days import Day
from src.models.entries import TicketEntry
from src.models.settings import Settings
from src.models.teams import Team
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.settings import finish_setup, save_settings
from src.modules.storage.teams import TeamRepository
from src.modules.storage.users import UserRepository
from src.tests.users import HANS, PASCAL, PASSWORD, RAINER, USER

MONDAY = dt.date(2026, 11, 2)
TODAY = dt.date(2026, 11, 6)
DAYS = [MONDAY + dt.timedelta(days=offset) for offset in range(4)]  # Monday to Thursday


def at(day):
    return dt.datetime.combine(day, dt.time(9))


@pytest.fixture
def ids(database):
    """Rainer was in Platform on Monday and Tuesday, left on Wednesday and came back on Thursday; each day 8:00 worked.
    Hans is a user, Pascal root."""
    with database.transaction() as conn:
        users = UserRepository(conn)
        ids = {person.username: users.add(person, PASSWORD).id for person in (HANS, RAINER)}
        ids['pascal'] = users.add(PASCAL.model_copy(update={'role': 'root'}), PASSWORD).id
        ids['platform'] = TeamRepository(conn).add(Team(name='Platform')).id
        for day, action in ((DAYS[0], 'join'), (DAYS[2], 'leave'), (DAYS[3], 'join')):
            teams = TeamRepository(conn, clock=lambda day=day: at(day))
            teams.join(ids['rainer'], ids['platform']) if action == 'join' else teams.leave(ids['rainer'])
        save_settings(conn, ids['rainer'], Settings(balance_start=MONDAY))
        finish_setup(conn, ids['rainer'])
        days, entries = DayRepository(conn, ids['rainer']), EntryRepository(conn, ids['rainer'])
        for day in DAYS:
            days.save(Day(date=day, start=8 * 60, end=16 * 60 + 30, note='doctor'))
            entries.create(TicketEntry(date=day, ticket_key='TNG-1', duration=480, description='bug fix', coding=True))
    return ids


def client(database, today=TODAY):
    return testing.TestClient(create_app(database, auth=True, today=lambda: today, clock=lambda: at(today)))


@pytest.fixture
def app(database, ids):
    return client(database)


def logged_in(app, name):
    result = app.simulate_post('/api/auth/login', json={'login': name, 'password': PASSWORD})
    return {'wt_session': result.cookies['wt_session'].value}


def assign(app, cookies, team_id, user_id, until=None):
    return app.simulate_put(f'/api/admin/teams/{team_id}/auditors/{user_id}', cookies=cookies, json={'until': until})


@pytest.fixture
def hans(app, ids):
    """Hans, auditor of Platform until the end of November."""
    assign(app, logged_in(app, 'klara'), ids['platform'], ids['hans'], '2026-11-30')
    return logged_in(app, 'hans')


def test_an_admin_assigns_and_removes_auditors(app, ids):
    klara = logged_in(app, 'klara')
    assigned = assign(app, klara, ids['platform'], ids['hans'], '2026-11-30').json
    assert (assigned['team'], assigned['user'], assigned['until']) == ('Platform', 'Hans Dampf', '2026-11-30')
    assert [item['user'] for item in app.simulate_get('/api/admin/auditors', cookies=klara).json] == ['Hans Dampf']
    path = f'/api/admin/teams/{ids["platform"]}/auditors/{ids["hans"]}'
    assert app.simulate_delete(path, cookies=klara).status == falcon.HTTP_204
    assert app.simulate_get('/api/admin/auditors', cookies=klara).json == []
    log = [(entry['action'], entry['detail']) for entry in app.simulate_get('/api/admin/audit', cookies=klara).json]
    assert log == [('auditor_removed', ''), ('auditor_assigned', '2026-11-30')]


def test_an_auditor_sees_each_stay_and_nothing_in_between(app, ids, hans):
    member = {'member': ids['rainer']}
    entries = app.simulate_get('/api/entries', cookies=hans, params=member | {'week': '2026-W45'}).json
    assert [entry['date'] for entry in entries] == ['2026-11-02', '2026-11-03', '2026-11-05']
    days = app.simulate_get('/api/days', cookies=hans, params=member | {'week': '2026-W45'}).json
    assert [(day['date'], day['in_team'], day['note']) for day in days[:4]] == [
        ('2026-11-02', True, ''), ('2026-11-03', True, ''), ('2026-11-04', False, ''), ('2026-11-05', True, '')]
    week = app.simulate_get('/api/reports/weeks/2026-W45', cookies=hans, params=member).json
    assert (week['totals']['worked'], week['visible_from']) == ('24:00', '2026-11-02')
    assert app.simulate_get('/api/reports/months/2026-11', cookies=hans, params=member).json['coding_total'] == '24:00'


def test_the_auditor_finds_the_team_with_its_members_and_their_stays(app, ids, hans):
    [team] = app.simulate_get('/api/audits', cookies=hans).json
    assert (team['team'], team['until'], [member['name'] for member in team['members']]) == (
        'Platform', '2026-11-30', ['Rainer Zufall'])
    assert team['members'][0]['stays'] == [{'joined_on': '2026-11-02', 'left_on': '2026-11-04'},
                                           {'joined_on': '2026-11-05', 'left_on': None}]


def test_members_see_who_audits_and_who_looked(app, ids, hans):
    app.simulate_get('/api/reports/weeks/2026-W45', cookies=hans, params={'member': ids['rainer']})
    mine = app.simulate_get('/api/team', cookies=logged_in(app, 'rainer')).json
    assert mine['auditors'] == [{'name': 'Hans Dampf', 'team': 'Platform', 'until': '2026-11-30'}]
    assert [view['viewer'] for view in mine['viewed_by']] == ['Hans Dampf']


def test_the_access_ends_after_the_last_day(database, ids, hans):
    later = client(database, today=dt.date(2026, 12, 1))
    hans = logged_in(later, 'hans')  # a new login: the old session has ended meanwhile
    result = later.simulate_get('/api/reports/weeks/2026-W45', cookies=hans, params={'member': ids['rainer']})
    assert result.status == falcon.HTTP_403
    assert later.simulate_get('/api/audits', cookies=hans).json == []


def test_others_still_do_not_see_the_team(app, ids, hans):
    result = app.simulate_get('/api/dashboard', cookies=logged_in(app, 'rainer'), params={'member': ids['hans']})
    assert result.status == falcon.HTTP_403  # being audited gives no view of the auditor


@pytest.mark.parametrize('who, user, message', [
    ('klara', USER, 'You cannot make yourself an auditor; ask another admin'),
    ('klara', 'pascal', 'Root tracks no work and audits no team'),
])
def test_not_oneself_and_not_root(app, ids, who, user, message):
    result = assign(app, logged_in(app, who), ids['platform'], ids.get(user, user))
    assert (result.status, result.json['description']) == (falcon.HTTP_409, message)


@pytest.mark.parametrize('who', ['hans', 'pascal'])
def test_only_admins_assign_auditors(app, ids, who):
    assert assign(app, logged_in(app, who), ids['platform'], ids['rainer']).status == falcon.HTTP_403
