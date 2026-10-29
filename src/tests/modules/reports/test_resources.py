import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.models.entries import TicketEntry
from src.modules.storage.catalog import ServiceRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.settings import load_settings, save_settings
from src.tests.users import USER

TODAY = dt.date(2026, 10, 28)


@pytest.fixture
def client(database):
    """Reports up to 28.10.2026; the balance starts on 01.10.2026."""
    with database.transaction() as conn:
        settings = load_settings(conn, USER)
        save_settings(conn, USER, settings.model_copy(update={'balance_start': dt.date(2026, 10, 1)}))
    return testing.TestClient(create_app(database, today=lambda: TODAY))


@pytest.fixture
def service_ids(database):
    with database.transaction() as conn:
        return {service.short_name: service.id for service in ServiceRepository(conn, USER).all()}


def work(client, date, start='08:00', end='16:30', break_time='0:30'):
    body = {'start': start, 'end': end, 'break_time': break_time}
    assert client.simulate_put(f'/api/days/{date}', json=body).status == falcon.HTTP_200


def ticket(client, date, key, duration, description='', coding=True, **extra):
    body = {'kind': 'ticket', 'date': date, 'duration': duration, 'ticket_key': key, 'description': description,
            'coding': coding}
    assert client.simulate_post('/api/entries', json=body | extra).status == falcon.HTTP_201


def test_week_counts_up_to_today(client):
    work(client, '2026-10-26', end='17:00')
    work(client, '2026-10-27', end='16:00')
    work(client, '2026-10-29')
    report = client.simulate_get('/api/reports/weeks/2026-W44').json
    # before: 17 weekdays from 01.10. without record (−8:00 each);
    # 26.10. +0:30, 27.10. −0:30, 28.10. (today, no times) −8:00; 29.10. is in the future
    assert report['totals'] == {
        'start': '2026-10-26', 'end': '2026-11-01', 'until': '2026-10-28',
        'worked': '16:00', 'target': '24:00', 'overtime': '-8:00', 'balance_in': '-136:00', 'balance_out': '-144:00',
    }


def test_week_days_off_include_planned_days(client):
    client.simulate_put('/api/days/2026-11-02', json={'day_type': 'pto'})
    client.simulate_put('/api/days/2026-11-03', json={'day_type': 'pto_half', 'start': '08:00', 'end': '12:00'})
    assert client.simulate_get('/api/reports/weeks/2026-W45').json['days_off'] == {'pto': 1, 'pto_half': 1}


def test_future_week_counts_nothing(client):
    totals = client.simulate_get('/api/reports/weeks/2026-W50').json['totals']
    assert (totals['until'], totals['worked'], totals['target']) == (None, '0:00', '0:00')
    assert totals['balance_in'] == totals['balance_out']


@pytest.mark.parametrize('path', ['/api/reports/weeks/2026-W54', '/api/reports/weeks/2026-44', '/api/reports/months/2026-13',
                                  '/api/reports/years/26'])
def test_invalid_period(client, path):
    assert client.simulate_get(path).status == falcon.HTTP_404


def test_month_coding_work_by_service_and_ticket(client, service_ids):
    ticket(client, '2026-10-05', 'ENGINE-573', '5:00', 'HUB support', service_id=service_ids['MSB'])
    ticket(client, '2026-10-06', 'ENGINE-573', '2:00', 'HUB support')
    ticket(client, '2026-10-06', 'ENGINE-565', '1:00', 'PR review')
    ticket(client, '2026-10-07', 'TNG-5783', '1:00', 'content type alias', service_id=service_ids['HiS'])
    ticket(client, '2026-10-07', 'ENGINE-594', '1:00', 'test access', service_id=service_ids['MSB'])
    ticket(client, '2026-10-08', 'KP-2203', '2:00', 'refinement', coding=False)
    ticket(client, '2026-11-02', 'ENGINE-573', '3:00', 'next month')
    report = client.simulate_get('/api/reports/months/2026-10').json
    assert report['coding'] == [
        {'service_id': service_ids['HiS'], 'service': 'HiS', 'duration': '1:00', 'tickets': [
            {'ticket_key': 'TNG-5783', 'duration': '1:00', 'descriptions': ['content type alias']},
        ]},
        {'service_id': service_ids['MSB'], 'service': 'MSB', 'duration': '8:00', 'tickets': [
            {'ticket_key': 'ENGINE-573', 'duration': '7:00', 'descriptions': ['HUB support']},
            {'ticket_key': 'ENGINE-594', 'duration': '1:00', 'descriptions': ['test access']},
        ]},
        {'service_id': None, 'service': None, 'duration': '1:00', 'tickets': [
            {'ticket_key': 'ENGINE-565', 'duration': '1:00', 'descriptions': ['PR review']},
        ]},
    ]
    assert report['coding_total'] == '10:00'


def test_month_lists_pr_reviews_without_ticket_last(client, database):
    ticket(client, '2026-10-05', 'TNG-999', '1:00')
    with database.transaction() as conn:
        review = TicketEntry(date=dt.date(2026, 10, 6), duration=120, description='PR reviews', coding=True)
        EntryRepository(conn, USER).create(review)
    [unassigned] = client.simulate_get('/api/reports/months/2026-10').json['coding']
    assert [(work['ticket_key'], work['duration']) for work in unassigned['tickets']] == [('TNG-999', '1:00'), (None, '2:00')]


def test_month_totals_days_off_and_pto(client):
    work(client, '2026-10-01', end='17:30')
    client.simulate_put('/api/days/2026-10-02', json={'day_type': 'pto'})
    client.simulate_put('/api/days/2026-10-05', json={'day_type': 'pto_half', 'start': '08:00', 'end': '12:00'})
    client.simulate_put('/api/days/2026-10-30', json={'day_type': 'sick'})
    report = client.simulate_get('/api/reports/months/2026-10').json
    assert report['days_off'] == {'pto': 1, 'pto_half': 1, 'sick': 1}
    assert report['pto_days'] == 1.5
    assert (report['totals']['until'], report['totals']['balance_in']) == ('2026-10-28', '0:00')


def test_year_report(client):
    work(client, '2026-10-01', end='17:30')
    work(client, '2026-10-02', end='15:30')
    report = client.simulate_get('/api/reports/years/2026').json
    assert [month['month'] for month in report['months']] == [f'2026-{month:02d}' for month in range(1, 13)]
    assert report['months'][0] == {'month': '2026-01', 'worked': '0:00', 'target': '0:00', 'overtime': '0:00'}
    assert (report['days_worked'], report['average_per_day_worked']) == (2, '8:00')
    assert report['totals']['balance_in'] == '0:00'


def test_year_days_before_balance_start_are_ignored(client):
    report = client.simulate_get('/api/reports/years/2026').json
    # from 01.10.: Heiligabend and Silvester, 25.12. (a Friday); 03.10. and 26.12. are Saturdays
    assert report['days_off'] == {'company_half_day': 2, 'public_holiday': 1}
    assert report['totals']['target'] == '160:00'  # 20 weekdays from 01.10. to 28.10.


def test_year_pto_account(client):
    client.simulate_put('/api/pto-years/2026', json={'allowance': 30, 'extra_days': 1})
    client.simulate_put('/api/days/2026-10-02', json={'day_type': 'pto'})
    client.simulate_put('/api/days/2026-12-28', json={'day_type': 'pto'})
    pto = client.simulate_get('/api/reports/years/2026').json['pto']
    assert pto == {
        'carried_over': 0.0, 'carried_over_fixed': False, 'allowance': 30.0, 'extra_days': 1.0, 'used': 1.0,
        'planned': 2.0, 'remaining': 28.0,
    }


def test_year_pto_account_with_fixed_carry_over(client):
    client.simulate_put('/api/pto-years/2026', json={'allowance': 30, 'carried_over': 3})
    pto = client.simulate_get('/api/reports/years/2026').json['pto']
    assert (pto['carried_over'], pto['carried_over_fixed'], pto['remaining']) == (3.0, True, 32.0)


def test_year_without_pto_days_entered(client, database):
    with database.transaction() as conn:
        conn.execute('DELETE FROM pto_years WHERE year = 2026')
    assert client.simulate_get('/api/reports/years/2026').json['pto'] is None


@pytest.mark.parametrize('year', [2025, 2027])
def test_year_pto_outside_balance_years(client, year):
    assert client.simulate_get(f'/api/reports/years/{year}').json['pto'] is None


def test_reports_are_documented(client):
    paths = client.simulate_get('/apidoc/openapi.json').json['paths']
    assert {'/api/reports/weeks/{week}', '/api/reports/months/{month}', '/api/reports/years/{year}'} <= set(paths)


def test_month_descriptions_are_merged_ignoring_case(client):
    ticket(client, '2026-10-07', 'ENGINE-565', '1:00', 'PR Review')
    ticket(client, '2026-10-15', 'ENGINE-565', '1:00', 'PR review')
    ticket(client, '2026-10-19', 'ENGINE-565', '2:00', 'WAF/ACL deployment')
    [unassigned] = client.simulate_get('/api/reports/months/2026-10').json['coding']
    assert unassigned['tickets'][0]['descriptions'] == ['PR Review', 'WAF/ACL deployment']
