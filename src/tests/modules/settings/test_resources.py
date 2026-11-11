import pytest


def test_get_settings(client):
    assert client.simulate_get('/api/settings').json == {
        'balance_start': '2024-06-01', 'opening_balance': '0:00', 'work_mode': 'tickets'}


def test_put_settings(client):
    expected = {'balance_start': '2027-03-01', 'opening_balance': '-1:45', 'work_mode': 'activities'}
    assert client.simulate_put('/api/settings', json=expected).json == expected
    assert client.simulate_get('/api/settings').json == expected


def test_reports_count_from_the_new_start_day(client):
    body = {'balance_start': '2026-10-26', 'opening_balance': '2:00', 'work_mode': 'tickets'}
    client.simulate_put('/api/settings', json=body)
    totals = client.simulate_get('/api/reports/weeks/2026-W44').json['totals']
    assert totals['balance_in'] == '2:00'


def test_theme_follows_the_system_by_default(client):
    assert client.simulate_get('/api/theme').json == {'theme': 'system'}


def test_choose_the_theme(client):
    assert client.simulate_put('/api/theme', json={'theme': 'dark'}).json == {'theme': 'dark'}
    assert client.simulate_get('/api/theme').json == {'theme': 'dark'}
    assert client.simulate_put('/api/theme', json={'theme': 'blue'}).status_code == 422


def test_saving_the_balance_keeps_the_theme(client):
    client.simulate_put('/api/theme', json={'theme': 'dark'})
    body = {'balance_start': '2027-03-01', 'opening_balance': '0:00', 'work_mode': 'tickets'}
    client.simulate_put('/api/settings', json=body)
    assert client.simulate_get('/api/theme').json == {'theme': 'dark'}


@pytest.mark.parametrize('theme, html', [('dark', '<html lang="en" data-theme="dark">'), ('system', '<html lang="en">')])
def test_pages_carry_the_theme(client, theme, html):
    client.simulate_put('/api/theme', json={'theme': theme})
    assert html in client.simulate_get('/settings').text
