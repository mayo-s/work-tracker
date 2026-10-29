import falcon
import pytest

SUMMER = {'start': '2026-07-11', 'end': '2026-08-02', 'day_type': 'pto', 'note': 'summer holidays'}


def book(client, body):
    return client.simulate_post('/api/days/range', json=body)


def entry(client, date):
    body = {'kind': 'ticket', 'date': date, 'duration': '1:00', 'ticket_key': 'TNG-5882'}
    assert client.simulate_post('/api/entries', json=body).status == falcon.HTTP_201


def test_books_the_work_days_like_the_hr_booking(client):
    result = book(client, SUMMER).json
    assert (result['saved'], len(result['days']), result['pto_days']) == (True, 15, 15.0)
    assert (result['days'][0], result['days'][-1]) == ('2026-07-13', '2026-07-31')
    assert {day['reason'] for day in result['left_out']} == {'day_off'}  # the weekends
    day = client.simulate_get('/api/days/2026-07-13').json
    assert (day['day_type'], day['automatic'], day['note'], day['target']) == ('pto', False, 'summer holidays', '0:00')
    assert client.simulate_get('/api/days/2026-07-11').json['recorded'] is False


def test_preview_saves_nothing(client):
    result = book(client, SUMMER | {'preview': True}).json
    assert (result['saved'], len(result['days'])) == (False, 15)
    assert client.simulate_get('/api/days/2026-07-13').json['recorded'] is False


def test_holidays_and_company_half_days_stay_automatic(client):
    result = book(client, {'start': '2026-12-21', 'end': '2027-01-01', 'day_type': 'pto'}).json
    assert result['days'] == ['2026-12-21', '2026-12-22', '2026-12-23', '2026-12-28', '2026-12-29', '2026-12-30']
    assert [(day['date'], day['reason']) for day in result['left_out'] if day['reason'] != 'day_off'] == [
        ('2026-12-24', 'company_half_day'), ('2026-12-25', 'public_holiday'), ('2026-12-31', 'company_half_day'),
        ('2027-01-01', 'public_holiday')]
    assert client.simulate_get('/api/days/2026-12-24').json['day_type'] == 'company_half_day'


def test_days_with_times_or_entries_are_refused_by_default(client):
    client.simulate_put('/api/days/2026-07-14', json={'start': '08:00', 'end': '16:30'})
    entry(client, '2026-07-15')
    result = book(client, SUMMER)
    assert result.status == falcon.HTTP_409
    assert result.json['description'] == '2 days hold times or entries: 14.07.2026, 15.07.2026'
    assert client.simulate_get('/api/days/2026-07-13').json['recorded'] is False


def test_preview_lists_the_conflicts(client):
    client.simulate_put('/api/days/2026-07-14', json={'start': '08:00', 'end': '16:30'})
    entry(client, '2026-07-14')
    result = book(client, SUMMER | {'preview': True}).json
    assert result['conflicts'] == [{'date': '2026-07-14', 'weekday': 'Tue', 'worked': '8:00', 'entries': 1}]
    assert (len(result['days']), result['pto_days']) == (14, 14.0)


def test_skip_leaves_the_conflicts_as_they_are(client):
    client.simulate_put('/api/days/2026-07-14', json={'start': '08:00', 'end': '16:30'})
    result = book(client, SUMMER | {'conflicts': 'skip'}).json
    assert '2026-07-14' not in result['days']
    assert client.simulate_get('/api/days/2026-07-14').json['day_type'] == 'work'


def test_include_books_the_conflicts_and_keeps_times_entries_and_note(client):
    client.simulate_put('/api/days/2026-07-14', json={'start': '08:00', 'end': '10:00', 'note': 'release'})
    entry(client, '2026-07-14')
    result = book(client, SUMMER | {'conflicts': 'include'}).json
    assert (len(result['days']), result['pto_days']) == (15, 15.0)
    day = client.simulate_get('/api/days/2026-07-14').json
    assert (day['day_type'], day['start'], day['note'], day['overtime']) == ('pto', '08:00', 'release', '2:00')
    assert len(client.simulate_get('/api/entries', params={'start': '2026-07-14', 'end': '2026-07-14'}).json) == 1


def test_a_day_with_only_a_day_type_is_replaced(client):
    client.simulate_put('/api/days/2026-07-14', json={'day_type': 'sick'})
    result = book(client, SUMMER).json
    assert (result['saved'], result['conflicts']) == (True, [])
    assert client.simulate_get('/api/days/2026-07-14').json['day_type'] == 'pto'


def test_sick_days_use_no_pto(client):
    result = book(client, {'start': '2026-10-05', 'end': '2026-10-09', 'day_type': 'sick'}).json
    assert (len(result['days']), result['pto_days']) == (5, 0.0)


@pytest.mark.parametrize('body', [
    SUMMER | {'day_type': 'pto_half'},
    SUMMER | {'day_type': 'work'},
    SUMMER | {'start': '2026-08-03'},
    SUMMER | {'start': '2025-01-01', 'end': '2026-01-02'},
    SUMMER | {'conflicts': 'overwrite'},
    SUMMER | {'unknown': 1},
])
def test_rejects_invalid_ranges(client, body):
    assert book(client, body).status_code == 422


def test_range_is_documented(client):
    assert set(client.simulate_get('/apidoc/openapi.json').json['paths']['/api/days/range']) == {'post'}
