import datetime as dt

import falcon
import pytest

from src.models.review import FlagReason
from src.modules.storage.days import DayRepository

WORK_DAY = {'start': '07:15', 'end': '16:00', 'break_time': '0:30', 'note': 'OFFICE DAY'}


def test_week_lists_every_day(client):
    result = client.simulate_get('/api/days', params={'week': '2026-W44'})
    assert result.status == falcon.HTTP_200
    assert [day['date'] for day in result.json] == [f'2026-10-{day}' for day in range(26, 32)] + ['2026-11-01']
    assert [day['target'] for day in result.json] == ['8:00'] * 5 + ['0:00'] * 2


def test_range_includes_recorded_days(client):
    client.simulate_put('/api/days/2026-10-28', json=WORK_DAY)
    result = client.simulate_get('/api/days', params={'start': '2026-10-27', 'end': '2026-10-28'})
    assert [(day['recorded'], day['worked']) for day in result.json] == [(False, '0:00'), (True, '8:15')]


@pytest.mark.parametrize('params', [{}, {'week': '2026-44'}, {'start': '2026-10-31', 'end': '2026-10-01'}])
def test_invalid_range(client, params):
    assert client.simulate_get('/api/days', params=params).status_code == 422


def test_get_unrecorded_day(client):
    result = client.simulate_get('/api/days/2026-12-24')
    assert result.status == falcon.HTTP_200
    expected = (False, 'Christmas Eve', 'company_half_day')
    assert (result.json['recorded'], result.json['holiday'], result.json['day_type']) == expected


def test_put_records_day(client):
    result = client.simulate_put('/api/days/2026-10-28', json=WORK_DAY)
    assert result.status == falcon.HTTP_200
    assert (result.json['start'], result.json['worked'], result.json['overtime'], result.json['note']) == (
        '07:15', '8:15', '0:15', 'OFFICE DAY')
    assert client.simulate_get('/api/days/2026-10-28').json == result.json


def test_put_without_break_uses_legal_minimum(client):
    result = client.simulate_put('/api/days/2026-10-28', json={'start': '08:00', 'end': '17:45'})
    assert (result.json['break_time'], result.json['break_default'], result.json['worked']) == ('0:45', True, '9:00')


def test_put_replaces_day(client):
    client.simulate_put('/api/days/2026-10-28', json=WORK_DAY)
    result = client.simulate_put('/api/days/2026-10-28', json={'day_type': 'pto'})
    assert (result.json['day_type'], result.json['start'], result.json['target'], result.json['pto_days']) == (
        'pto', None, '0:00', 1.0)


@pytest.mark.parametrize('body', [
    {'start': '16:00', 'end': '08:00'},
    {'start': '08:00'},
    {'start': '25:00', 'end': '26:00'},
    {'day_type': 'holiday'},
    {'pause': 30},
])
def test_put_rejects_invalid_day(client, body):
    assert client.simulate_put('/api/days/2026-10-28', json=body).status_code == 422


def test_put_explains_invalid_times(client):
    result = client.simulate_put('/api/days/2026-10-28', json={'start': '16:00', 'end': '08:00'})
    assert 'is before start' in result.json[0]['msg']


@pytest.mark.parametrize('path', ['/api/days/28.10.2026', '/api/days/2026-02-30'])
def test_invalid_date_in_path(client, path):
    assert client.simulate_get(path).status == falcon.HTTP_404


def test_delete_day_and_its_flags(client, database):
    client.simulate_put('/api/days/2025-12-06', json={'start': '08:00', 'end': '11:30', 'break_time': '0:00'})
    with database.transaction() as conn:
        DayRepository(conn).add_flag(dt.date(2025, 12, 6), FlagReason.WEEKEND_HOURS, '3,5 ABREISE Lübeck')
    assert client.simulate_get('/api/days/2025-12-06').json['flags'][0]['reason'] == 'weekend_hours'
    assert client.simulate_delete('/api/days/2025-12-06').status == falcon.HTTP_204
    assert client.simulate_get('/api/days/2025-12-06').json['flags'] == []


def test_delete_unrecorded_day(client):
    result = client.simulate_delete('/api/days/2026-10-28')
    assert result.status == falcon.HTTP_404
    assert result.json['description'] == 'No day recorded on 2026-10-28'


def test_days_are_documented(client):
    paths = client.simulate_get('/apidoc/openapi.json').json['paths']
    assert set(paths['/api/days']) == {'get'}
    assert set(paths['/api/days/{date}']) == {'get', 'put', 'delete'}
