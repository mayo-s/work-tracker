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
    {'balance_start': '2027-03-01', 'opening_balance': '1:5'},
    {'balance_start': '01.03.2027', 'opening_balance': '0:00'},
    {'balance_start': '2027-03-01'},
    {'balance_start': '2027-03-01', 'opening_balance': '0:00', 'unknown': 1},
])
def test_put_rejects_invalid_settings(client, body):
    assert client.simulate_put('/api/settings', json=body).status_code == 422


def test_settings_are_documented(client):
    assert set(client.simulate_get('/apidoc/openapi.json').json['paths']['/api/settings']) == {'get', 'put'}


def test_theme_follows_the_system_by_default(client):
    assert client.simulate_get('/api/theme').json == {'theme': 'system'}


@pytest.mark.parametrize('theme', ['dark', 'light', 'system'])
def test_choose_the_theme(client, theme):
    assert client.simulate_put('/api/theme', json={'theme': theme}).json == {'theme': theme}
    assert client.simulate_get('/api/theme').json == {'theme': theme}


@pytest.mark.parametrize('body', [{'theme': 'blue'}, {}, {'theme': 'dark', 'unknown': 1}])
def test_choose_rejects_invalid_themes(client, body):
    assert client.simulate_put('/api/theme', json=body).status_code == 422


def test_saving_the_balance_keeps_the_theme(client):
    client.simulate_put('/api/theme', json={'theme': 'dark'})
    client.simulate_put('/api/settings', json={'balance_start': '2027-03-01', 'opening_balance': '0:00'})
    assert client.simulate_get('/api/theme').json == {'theme': 'dark'}


@pytest.mark.parametrize('theme, html', [('dark', '<html lang="en" data-theme="dark">'),
                                         ('light', '<html lang="en" data-theme="light">'),
                                         ('system', '<html lang="en">')])
def test_pages_carry_the_theme(client, theme, html):
    client.simulate_put('/api/theme', json={'theme': theme})
    assert html in client.simulate_get('/settings').text
