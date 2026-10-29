"""Team view (L.10): a team admin sees a member's data read-only, from the day the member joined the team."""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.models.days import Day
from src.models.entries import TicketEntry
from src.models.teams import Team
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.settings import finish_setup, save_settings
from src.models.settings import Settings
from src.modules.storage.teams import TeamRepository
from src.modules.storage.users import UserRepository
from src.tests.users import HANS, PASCAL, PASSWORD, RAINER

JOINED = dt.datetime(2026, 11, 4, 9, 0)  # a Wednesday
TODAY = dt.date(2026, 11, 6)
BEFORE, AFTER = dt.date(2026, 11, 2), dt.date(2026, 11, 5)


@pytest.fixture
def ids(database):
    """Hans is team admin of Platform, Rainer joined it on 4.11.; Rainer has a day and an entry before and after."""
    with database.transaction() as conn:
        users = UserRepository(conn)
        ids = {person.username: users.add(person, PASSWORD).id for person in (HANS, RAINER, PASCAL)}
        teams = TeamRepository(conn, clock=lambda: JOINED)
        platform = teams.add(Team(name='Platform')).id
        for name in ('hans', 'rainer'):
            teams.join(ids[name], platform)
        users.set_role(ids['hans'], 'team_admin')
        save_settings(conn, ids['rainer'], Settings(balance_start=dt.date(2026, 11, 2)))
        finish_setup(conn, ids['rainer'])
        days, entries = DayRepository(conn, ids['rainer']), EntryRepository(conn, ids['rainer'])
        for date in (BEFORE, AFTER):
            days.save(Day(date=date, start=8 * 60, end=16 * 60 + 30, note='doctor at 7'))  # 8:00 worked
            entries.create(TicketEntry(date=date, ticket_key='TNG-1', duration=480, description='bug fix', coding=True))
    return ids


@pytest.fixture
def app(database, ids):
    return testing.TestClient(create_app(database, auth=True, today=lambda: TODAY,
                                         clock=lambda: dt.datetime(2026, 11, 6, 12, 0)))


def logged_in(app, name):
    result = app.simulate_post('/api/auth/login', json={'login': name, 'password': PASSWORD})
    return {'wt_session': result.cookies['wt_session'].value}


@pytest.fixture
def hans(app):
    return logged_in(app, 'hans')


def week(app, cookies, member, path='/api/days'):
    return app.simulate_get(path, cookies=cookies, params={'week': '2026-W45'} | ({'member': member} if member else {}))


def test_days_before_joining_show_no_data_and_notes_stay_hidden(app, hans, ids):
    days = {day['date']: day for day in week(app, hans, ids['rainer']).json}
    before, after = days[BEFORE.isoformat()], days[AFTER.isoformat()]
    assert (before['in_team'], before['start'], before['worked'], before['note']) == (False, None, '0:00', '')
    assert (after['in_team'], after['start'], after['worked'], after['note']) == (True, '08:00', '8:00', '')


def test_entries_from_joining_on(app, hans, ids):
    entries = week(app, hans, ids['rainer'], '/api/entries').json
    assert [(entry['date'], entry['description']) for entry in entries] == [(AFTER.isoformat(), 'bug fix')]


def test_reports_count_from_joining_on(app, hans, ids):
    totals = app.simulate_get('/api/reports/weeks/2026-W45', cookies=hans, params={'member': ids['rainer']}).json['totals']
    assert (totals['worked'], totals['target']) == ('8:00', '24:00')  # Wednesday (no time) to Friday (today)
    month = app.simulate_get('/api/reports/months/2026-11', cookies=hans, params={'member': ids['rainer']}).json
    assert (month['coding_total'], month['visible_from']) == ('8:00', '2026-11-04')


def test_dashboard_without_review_items(app, hans, ids):
    dashboard = app.simulate_get('/api/dashboard', cookies=hans, params={'member': ids['rainer']}).json
    assert (dashboard['review_open'], dashboard['visible_from']) == (0, '2026-11-04')


def test_member_sees_who_can_look_and_who_looked(app, hans, ids):
    app.simulate_get('/api/reports/weeks/2026-W45', cookies=hans, params={'member': ids['rainer']})
    app.simulate_get('/api/dashboard', cookies=hans)  # their own: not logged
    mine = app.simulate_get('/api/team', cookies=logged_in(app, 'rainer')).json
    assert mine['team_admins'] == ['Hans Dampf']
    assert mine['viewed_by'] == [{'viewer': 'Hans Dampf', 'report': 'week', 'period': '2026-W45',
                                  'viewed_at': '2026-11-06T12:00:00'}]


@pytest.mark.parametrize('viewer, member', [
    ('rainer', 'hans'),  # a member, not team admin
    ('klara', 'rainer'),  # the admin, not team admin of the team
    ('hans', 'pascal'),  # not in the team
])
def test_others_are_refused(app, ids, viewer, member):
    result = app.simulate_get('/api/dashboard', cookies=logged_in(app, viewer), params={'member': ids[member]})
    assert result.status == falcon.HTTP_403


def test_former_members_drop_out(app, hans, ids):
    app.simulate_delete('/api/team', cookies=logged_in(app, 'rainer'))
    assert week(app, hans, ids['rainer']).status == falcon.HTTP_403


def test_own_data_is_unchanged(app, ids):
    days = {day['date']: day for day in week(app, logged_in(app, 'rainer'), None).json}
    assert (days[BEFORE.isoformat()]['start'], days[BEFORE.isoformat()]['note']) == ('08:00', 'doctor at 7')
