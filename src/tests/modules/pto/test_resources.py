import falcon
import pytest


def test_list_years(client):
    years = client.simulate_get('/api/pto-years').json
    assert [(year['year'], year['allowance']) for year in years] == [(2024, 17.5), (2025, 31.0), (2026, 31.0), (2027, 30.0)]


def test_get_year(client):
    assert client.simulate_get('/api/pto-years/2024').json == {
        'allowance': 17.5, 'extra_days': 0.0, 'carried_over': None, 'note': '', 'year': 2024,
    }


def test_get_missing_year(client):
    assert client.simulate_get('/api/pto-years/2023').status == falcon.HTTP_404


def test_put_inserts_and_replaces(client):
    body = {'allowance': 30, 'extra_days': 1, 'carried_over': 3, 'note': 'one extra day granted'}
    assert client.simulate_put('/api/pto-years/2026', json=body).json == body | {'year': 2026}
    assert client.simulate_put('/api/pto-years/2028', json={'allowance': 30}).status == falcon.HTTP_200
    assert client.simulate_get('/api/pto-years/2026').json['carried_over'] == 3
    assert client.simulate_get('/api/pto-years/2028').json['extra_days'] == 0


@pytest.mark.parametrize('body', [{'allowance': -1}, {'allowance': 17.25}, {}, {'allowance': 30, 'unknown': 1}])
def test_put_rejects_invalid_days(client, body):
    assert client.simulate_put('/api/pto-years/2026', json=body).status_code == 422


def test_delete_year(client):
    assert client.simulate_delete('/api/pto-years/2027').status == falcon.HTTP_204
    assert client.simulate_get('/api/pto-years/2027').status == falcon.HTTP_404
    assert client.simulate_delete('/api/pto-years/2027').status == falcon.HTTP_404


def test_pto_years_are_documented(client):
    paths = client.simulate_get('/apidoc/openapi.json').json['paths']
    assert {'/api/pto-years', '/api/pto-years/{year}'} <= set(paths)
