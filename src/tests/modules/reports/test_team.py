"""The team report (SPEC 5.12): the whole app on SQLite and on DynamoDB (moto).

Hans is team admin of Platform from Monday 2.11.; Rainer joined on Wednesday; Klara was in it on Monday and Tuesday.
Pascal audits it, today is Friday 6.11.
"""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.lib.daytypes import DayType
from src.models.catalog import CODING, Service, new_activity_type
from src.models.days import Day
from src.models.entries import Entry
from src.models.settings import Settings
from src.models.teams import Auditor, Team
from src.modules.reports.team import stay_note, team_report_file_name
from src.modules.teams.schemas import StayView
from src.tests.helpers import Clock, logged_in
from src.tests.ids import FIRST
from src.tests.users import HANS, KLARA, PASCAL, PASSWORD, RAINER

MONDAY = dt.date(2026, 11, 2)
TODAY = dt.date(2026, 11, 6)
NOVEMBER = {'month': '2026-11'}


def nov(day):
    return dt.date(2026, 11, day)


def at(day):
    return dt.datetime.combine(day, dt.time(9))


def worked_day(date):
    return Day(date=date, start=8 * 60, end=16 * 60 + 30, note='doctor at 7')  # 8:00 worked


def add_person(store, person):
    user_id = store.users().add(person.model_copy(update={'role': 'user'}), PASSWORD).id
    store.save_settings(user_id, Settings(balance_start=MONDAY))
    store.finish_setup(user_id)
    return user_id


def add_entries(store, user_id, activity_type, entries):
    """Entries of (day, ticket, minutes) of that activity type, by its name; a new one is added."""
    known = {kind.name: kind.id for kind in store.activity_types(user_id).all()}
    type_id = known.get(activity_type) or store.activity_types(user_id).add(new_activity_type(activity_type)).id
    for date, ticket, minutes in entries:
        store.entries(user_id).create(Entry(date=date, activity_type_id=type_id, ticket_key=ticket, duration=minutes,
                                            description='a secret text'))


@pytest.fixture
def ids(storage):
    with storage.transaction() as store:
        ids = {person.username: add_person(store, person) for person in (HANS, RAINER, KLARA, PASCAL)}
        platform = store.teams().add(Team(name='Platform')).id
        for name, day in (('hans', nov(2)), ('klara', nov(2)), ('rainer', nov(4))):
            store.teams(lambda day=day: at(day)).join(ids[name], platform)
        store.teams(lambda: at(nov(4))).leave(ids['klara'])
        store.teams(lambda: at(nov(2))).set_team_role(ids['hans'], 'team_admin')
        store.auditors().assign(Auditor(team_id=platform, user_id=ids['pascal'], assigned_by=ids['hans'],
                                        assigned_at=at(nov(2))))
    with storage.transaction() as store:
        fill_hans(store, ids['hans'])
    with storage.transaction() as store:
        fill_rainer(store, ids['rainer'])
    with storage.transaction() as store:
        for day in (nov(2), nov(4)):  # the day she left does not count
            store.days(ids['klara']).save(worked_day(day))
    return ids | {'platform': platform}


def fill_hans(store, hans):
    store.days(hans).save(worked_day(nov(2)))
    store.days(hans).save(worked_day(nov(3)))
    store.days(hans).save(Day(date=nov(4), day_type=DayType.SICK, note='flu'))
    add_entries(store, hans, CODING, [(nov(2), 'MSB-1', 180)])
    add_entries(store, hans, 'Meeting', [(nov(3), None, 60)])
    service = store.services(hans).add(Service(short_name='MSB')).id
    store.tickets(hans).set_service('MSB-1', service)


def fill_rainer(store, rainer):
    store.days(rainer).save(worked_day(nov(3)))  # the day before he joined does not count
    store.days(rainer).save(worked_day(nov(4)))
    add_entries(store, rainer, 'coding', [(nov(3), 'TNG-9', 480), (nov(4), 'TNG-1', 120), (nov(5), 'KP-2', 30),
                                          (nov(9), 'TNG-1', 60)])  # the last one is after today
    service = store.services(rainer).add(Service(short_name='msb')).id
    store.tickets(rainer).set_service('TNG-1', service)


@pytest.fixture
def app(storage, ids):
    return testing.TestClient(create_app(storage=storage, auth=True, today=lambda: TODAY, clock=Clock(at(TODAY))))


def report(app, ids, name, params=NOVEMBER):
    return app.simulate_get(f'/api/teams/{ids["platform"]}/report', cookies=logged_in(app, name), params=params)


def csv_report(app, ids, name, params=NOVEMBER):
    return app.simulate_get(f'/api/teams/{ids["platform"]}/report.csv', cookies=logged_in(app, name), params=params)


def test_the_notes_come_in_the_requests_language_but_the_csv_file_stays_english(app, ids):
    german, cookies, path = {'Accept-Language': 'de'}, logged_in(app, 'hans'), f'/api/teams/{ids["platform"]}/report'
    members = app.simulate_get(path, cookies=cookies, params=NOVEMBER, headers=german).json['members']
    csv = app.simulate_get(f'{path}.csv', cookies=cookies, params=NOVEMBER, headers=german).text
    assert ([member['note'] for member in members], 'Member;Hans Dampf;Note;from 02.11.' in csv) == (
        ['ab 02.11.', 'ab 04.11.'], True)


def test_a_team_admin_sees_the_current_members_from_the_day_they_joined(app, ids):
    result = report(app, ids, 'hans')
    assert result.status == falcon.HTTP_200
    assert result.json == {
        'team_id': ids['platform'], 'team': 'Platform', 'start': '2026-11-01', 'end': '2026-11-30', 'until': '2026-11-06',
        'current_members_only': True,
        'totals': {'worked': '24:00', 'target': '56:00', 'overtime': '-32:00', 'entries': '6:30'},
        'activity_types': [{'activity_type': 'Coding', 'duration': '5:30'},
                           {'activity_type': 'Meeting', 'duration': '1:00'}],
        'services': [
            {'service': 'MSB', 'duration': '5:00', 'tickets': [{'ticket_key': 'MSB-1', 'duration': '3:00'},
                                                               {'ticket_key': 'TNG-1', 'duration': '2:00'}]},
            {'service': None, 'duration': '0:30', 'tickets': [{'ticket_key': 'KP-2', 'duration': '0:30'}]},
        ],
        'members': [
            {'user_id': ids['hans'], 'name': 'Hans Dampf', 'stays': [{'joined_on': '2026-11-02', 'left_on': None}],
             'note': 'from 02.11.', 'worked': '16:00', 'target': '32:00', 'overtime': '-16:00', 'entries': '4:00',
             'activity_types': [{'activity_type': 'Coding', 'duration': '3:00'},
                                {'activity_type': 'Meeting', 'duration': '1:00'}]},
            {'user_id': ids['rainer'], 'name': 'Rainer Zufall', 'stays': [{'joined_on': '2026-11-04', 'left_on': None}],
             'note': 'from 04.11.', 'worked': '8:00', 'target': '24:00', 'overtime': '-16:00', 'entries': '2:30',
             'activity_types': [{'activity_type': 'coding', 'duration': '2:30'}]},
        ],
    }


def test_an_auditor_also_sees_former_members_for_the_days_of_their_stay(app, ids):
    result = report(app, ids, 'pascal').json
    assert result['current_members_only'] is False
    assert result['totals'] == {'worked': '32:00', 'target': '72:00', 'overtime': '-40:00', 'entries': '6:30'}
    klara = result['members'][1]
    assert (klara['name'], klara['stays']) == ('Klara Himmel', [{'joined_on': '2026-11-02', 'left_on': '2026-11-04'}])
    assert (klara['worked'], klara['target'], klara['entries'], klara['activity_types']) == ('8:00', '16:00', None, [])


@pytest.mark.parametrize('stays, note', [
    ([(dt.date(2026, 10, 1), None)], None),
    ([(dt.date(2026, 10, 1), dt.date(2026, 12, 1))], None),  # in it until the last day
    ([(nov(4), None)], 'from 04.11.'),
    ([(dt.date(2026, 10, 1), nov(4))], 'until 03.11.'),
    ([(nov(2), nov(4)), (nov(5), None)], '02.11.–03.11., from 05.11.'),
])
def test_a_note_only_for_someone_who_was_not_there_all_period(stays, note):
    views = [StayView(joined_on=joined, left_on=left) for joined, left in stays]
    assert stay_note(views, nov(1), nov(30)) == note


def test_the_report_holds_only_hours_and_is_not_logged(app, storage, ids):
    text = report(app, ids, 'hans').text
    assert [word for word in ('secret', 'doctor', 'flu', 'sick', 'balance', 'pto') if word in text] == []
    with storage.transaction() as store:
        assert store.report_views().of_member(ids['rainer']) == []


@pytest.mark.parametrize('params, worked, names', [
    ({'year': 2026}, '24:00', ['Hans Dampf', 'Rainer Zufall']),
    ({'month': '2026-10'}, '0:00', []),  # before anyone joined
    ({'month': '2026-12'}, '0:00', ['Hans Dampf', 'Rainer Zufall']),  # nothing counted yet
])
def test_periods(app, ids, params, worked, names):
    result = report(app, ids, 'hans', params).json
    assert (result['totals']['worked'], [member['name'] for member in result['members']]) == (worked, names)


def auditor_flag(app, name):
    return app.simulate_get('/api/auth/status', cookies=logged_in(app, name)).json['auditor']


def test_only_team_admins_and_active_auditors_of_the_team(app, storage, ids):
    assert (auditor_flag(app, 'pascal'), auditor_flag(app, 'hans')) == (True, False)  # the status shows the tab
    assert report(app, ids, 'rainer').status == falcon.HTTP_403  # a member
    assert report(app, ids, 'klara').status == falcon.HTTP_403  # a former member
    unknown = app.simulate_get(f'/api/teams/{FIRST}/report', cookies=logged_in(app, 'hans'), params=NOVEMBER)
    assert unknown.status == falcon.HTTP_403
    with storage.transaction() as store:
        store.auditors().assign(Auditor(team_id=ids['platform'], user_id=ids['pascal'], until=nov(5),
                                        assigned_by=ids['hans'], assigned_at=at(nov(2))))
    assert report(app, ids, 'pascal').status == falcon.HTTP_403  # the assignment ended yesterday
    assert auditor_flag(app, 'pascal') is False


@pytest.mark.parametrize('params', [{}, {'month': '2026-11', 'year': 2026}, {'month': '2026-13'}, {'year': 26}])
def test_the_period_is_a_month_or_a_year(app, ids, params):
    assert report(app, ids, 'hans', params).status_code == 422


def test_the_csv_has_one_row_per_figure_for_german_excel(app, ids):
    result = csv_report(app, ids, 'hans')
    assert result.status == falcon.HTTP_200
    assert result.headers['content-type'] == 'text/csv; charset=utf-8'
    assert result.headers['content-disposition'] == 'attachment; filename="20261106_0900_team_report_Platform.csv"'
    assert result.content.startswith('\N{BYTE ORDER MARK}Section;'.encode())
    assert result.content.decode('utf-8-sig').split('\r\n') == [
        'Section;Name;Figure;Duration',
        'Team;Platform;Period;01.11.2026–30.11.2026', 'Team;Platform;Counted up to;06.11.2026',
        'Team;Platform;Note;Current members only, each from the day they joined: the total of a past period shrinks when '
        'someone leaves.',
        'Team;Platform;Worked;24:00', 'Team;Platform;Target;56:00', 'Team;Platform;Overtime;-32:00',
        'Team;Platform;Entries;6:30',
        'Activity type;Coding;Total;5:30', 'Activity type;Meeting;Total;1:00',
        'Service;MSB;Total;5:00', 'Service;MSB;MSB-1;3:00', 'Service;MSB;TNG-1;2:00',
        'Service;No service;Total;0:30', 'Service;No service;KP-2;0:30',
        'Member;Hans Dampf;Note;from 02.11.', 'Member;Hans Dampf;Worked;16:00', 'Member;Hans Dampf;Target;32:00',
        'Member;Hans Dampf;Overtime;-16:00', 'Member;Hans Dampf;Entries;4:00',
        'Member;Hans Dampf;Coding;3:00', 'Member;Hans Dampf;Meeting;1:00',
        'Member;Rainer Zufall;Note;from 04.11.', 'Member;Rainer Zufall;Worked;8:00', 'Member;Rainer Zufall;Target;24:00',
        'Member;Rainer Zufall;Overtime;-16:00', 'Member;Rainer Zufall;Entries;2:30', 'Member;Rainer Zufall;coding;2:30',
        '',
    ]


@pytest.mark.parametrize('team, name', [
    ('Platform', '20261109_1407_team_report_Platform'),
    ('Büro Süd', '20261109_1407_team_report_Büro_Süd'),
    ('"a/b"\r\n', '20261109_1407_team_report_a_b'),
])
def test_the_file_name_holds_the_time_and_the_team(team, name):
    assert team_report_file_name(team, dt.datetime(2026, 11, 9, 14, 7)) == name


def test_the_csv_keeps_names_from_running_as_formulas(app, storage, ids):
    with storage.transaction() as store:
        add_entries(store, ids['hans'], '=SUM(A1;A2)', [(nov(2), None, 60)])
    rows = csv_report(app, ids, 'hans').content.decode('utf-8-sig').split('\r\n')
    assert 'Activity type;"\'=SUM(A1;A2)";Total;1:00' in rows
    assert 'Member;Hans Dampf;"\'=SUM(A1;A2)";1:00' in rows


def test_the_csv_is_for_the_same_people_and_periods(app, ids):
    assert csv_report(app, ids, 'rainer').status == falcon.HTTP_403
    assert csv_report(app, ids, 'hans', {}).status_code == 422
    assert 'Team;Platform;Period;01.01.2026–31.12.2026\r\n' in csv_report(app, ids, 'hans', {'year': 2026}).content.decode()
    auditor = csv_report(app, ids, 'pascal').content.decode('utf-8-sig')
    assert 'Member;Klara Himmel;Note;02.11.–03.11.\r\nMember;Klara Himmel;Worked;8:00\r\n' in auditor
    assert 'Current members only' not in auditor
    assert 'Member;Klara Himmel;Entries;\r\n' in auditor  # no hours in entries
