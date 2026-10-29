import pytest


def test_get_settings(client):
    assert client.simulate_get('/api/settings').json == {'balance_start': '2024-06-01', 'opening_balance': '0:00'}


@pytest.mark.parametrize('opening, shown', [('+12:30', '12:30'), ('-1:45', '-1:45'), ('0:00', '0:00')])
def test_put_settings(client, opening, shown):
    body = {'balance_start': '2027-03-01', 'opening_balance': opening}
    expected = {'balance_start': '2027-03-01', 'opening_balance': shown}
    assert client.simulate_put('/api/settings', json=body).json == expected
    assert client.simulate_get('/api/settings').json == expected


def test_reports_count_from_the_new_start_day(client):
    client.simulate_put('/api/settings', json={'balance_start': '2026-10-26', 'opening_balance': '2:00'})
    totals = client.simulate_get('/api/reports/weeks/2026-W44').json['totals']
    assert totals['balance_in'] == '2:00'


@pytest.mark.parametrize('body', [
    {'balance_start': '2027-03-01', 'opening_balance': '1,5'},
    {'balance_start': '01.03.2027', 'opening_balance': '0:00'},
    {'balance_start': '2027-03-01'},
    {'balance_start': '2027-03-01', 'opening_balance': '0:00', 'unknown': 1},
])
def test_put_rejects_invalid_settings(client, body):
    assert client.simulate_put('/api/settings', json=body).status_code == 422


def test_settings_are_documented(client):
    assert set(client.simulate_get('/apidoc/openapi.json').json['paths']['/api/settings']) == {'get', 'put'}
