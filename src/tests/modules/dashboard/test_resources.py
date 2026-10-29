import datetime as dt

import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.settings import load_settings, save_settings

TODAY = dt.date(2026, 10, 28)  # a Wednesday


@pytest.fixture
def client(database):
    """The dashboard on 28.10.2026; the balance starts on 01.09.2026 with 2:00 taken over."""
    with database.transaction() as conn:
        settings = load_settings(conn)
        save_settings(conn, settings.model_copy(update={'balance_start': dt.date(2026, 9, 1), 'opening_balance': 120}))
    return testing.TestClient(create_app(database, today=lambda: TODAY))


def work(client, date, start='08:00', end='16:30', break_time='0:30'):
    client.simulate_put(f'/api/days/{date}', json={'start': start, 'end': end, 'break_time': break_time})


def dashboard(client):
    return client.simulate_get('/api/dashboard').json


def test_key_figures(client):
    work(client, '2026-10-26', end='17:30')  # 9:00, +1:00
    work(client, '2026-10-27')  # 8:00
    result = dashboard(client)
    # 01.09.–28.10.: 42 weekdays, 40 of them without times (today too): 2:00 − 40 × 8:00 + 1:00
    assert (result['today'], result['week']) == ('2026-10-28', '2026-W44')
    assert result['balance'] == '-317:00'
    assert result['balance_change_this_year'] == '-319:00'  # since the opening balance of 2:00
    assert (result['this_week']['worked'], result['this_week']['target']) == ('17:00', '24:00')  # up to today
    assert result['week_target'] == '40:00'  # the whole week
    assert result['pto']['allowance'] == 31.0
    assert result['review_open'] == 0


def test_balance_series(client):
    series = dashboard(client)['balance_series']
    assert [point['date'] for point in series['all']] == ['2026-09-30', '2026-10-28']
    assert series['year'] == series['all']
    assert series['last_12_months'] == series['all']
    assert (series['month'][0]['date'], series['month'][-1]['date'], len(series['month'])) == ('2026-10-01', '2026-10-28', 28)
    # September: 22 weekdays without times; the opening balance counts
    assert series['all'][0] == {'date': '2026-09-30', 'minutes': 120 - 22 * 480, 'balance': '-174:00'}
    assert series['month'][-1]['balance'] == dashboard(client)['balance']


def test_coming_up_combines_days_in_a_row_and_keeps_holidays_apart(client):
    for date in ('2026-11-05', '2026-11-06', '2026-11-09'):  # Thursday, Friday and the Monday after the weekend
        client.simulate_put(f'/api/days/{date}', json={'day_type': 'pto'})
    client.simulate_put('/api/days/2026-11-11', json={'day_type': 'pto'})
    client.simulate_put('/api/days/2026-12-23', json={'day_type': 'pto'})
    items = [(item['start'], item['end'], item['day_type'], item['holiday'], item['days'])
             for item in dashboard(client)['coming_up']]
    assert items == [
        ('2026-11-05', '2026-11-09', 'pto', None, 3),
        ('2026-11-11', '2026-11-11', 'pto', None, 1),
        ('2026-12-23', '2026-12-23', 'pto', None, 1),
        ('2026-12-24', '2026-12-24', 'company_half_day', 'Christmas Eve', 1),
        ('2026-12-25', '2026-12-25', 'public_holiday', 'Christmas Day', 1),
    ]  # 26.12. is a Saturday; 27.12. is more than 60 days ahead


def test_this_year(client):
    work(client, '2026-10-26')
    client.simulate_put('/api/days/2026-10-05', json={'day_type': 'sick'})
    client.simulate_put('/api/days/2026-10-06', json={'day_type': 'sick_half', 'start': '08:00', 'end': '12:00'})
    body = {'kind': 'ticket', 'date': '2026-10-26', 'duration': '3:00', 'ticket_key': 'ENGINE-597', 'coding': True}
    client.simulate_post('/api/entries', json=body)
    figures = dashboard(client)['this_year']
    assert (figures['year'], figures['days_worked'], figures['sick_days']) == (2026, 2, 1.5)
    assert (figures['coding'], figures['top_services']) == ('3:00', [{'service': None, 'duration': '3:00'}])


def test_before_the_balance_start(client, database):
    with database.transaction() as conn:
        save_settings(conn, load_settings(conn).model_copy(update={'balance_start': dt.date(2027, 3, 1)}))
    result = dashboard(client)
    assert (result['balance'], result['balance_series']['all'], result['balance_series']['month']) == ('2:00', [], [])


def test_dashboard_is_documented(client):
    assert set(client.simulate_get('/apidoc/openapi.json').json['paths']['/api/dashboard']) == {'get'}


def test_week_target_counts_planned_days_off(client):
    client.simulate_put('/api/days/2026-10-30', json={'day_type': 'pto'})  # Friday
    assert dashboard(client)['week_target'] == '32:00'
