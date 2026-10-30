import falcon
import pytest

PART_TIME = {'valid_from': '2026-10-28', 'weekly_hours': '30:00', 'work_days': ['Mon', 'Tue', 'Wed', 'Thu']}


def test_list_schedules(client):
    [schedule] = client.simulate_get('/api/work-schedules').json
    assert schedule == {
        'id': schedule['id'], 'valid_from': '2024-06-01', 'weekly_hours': '40:00',
        'work_days': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], 'state': 'BE', 'company_half_days': True, 'daily_target': '8:00',
    }


def test_add_read_change_delete(client):
    created = client.simulate_post('/api/work-schedules', json=PART_TIME)
    assert created.status == falcon.HTTP_201
    path = created.headers['location']
    defaults = {'state': 'BE', 'company_half_days': True}
    assert created.json == PART_TIME | defaults | {'id': created.json['id'], 'daily_target': '7:30'}
    assert client.simulate_get(path).json == created.json
    changed = client.simulate_put(path, json=PART_TIME | {'work_days': ['Thu', 'Mon', 'Tue']}).json
    assert (changed['work_days'], changed['daily_target']) == (['Mon', 'Tue', 'Thu'], '10:00')
    assert client.simulate_delete(path).status == falcon.HTTP_204
    assert client.simulate_get(path).status == falcon.HTTP_404


def test_days_follow_the_new_schedule_from_its_start(client):
    client.simulate_post('/api/work-schedules', json=PART_TIME)
    days = client.simulate_get('/api/days', params={'week': '2026-W44'}).json
    assert [(day['weekday'], day['target'], day['work_day']) for day in days[1:5]] == [
        ('Tue', '8:00', True), ('Wed', '7:30', True), ('Thu', '7:30', True), ('Fri', '0:00', False)]


def test_report_counts_days_off_on_work_days_only(client):
    client.simulate_post('/api/work-schedules', json=PART_TIME)
    client.simulate_put('/api/days/2026-10-29', json={'day_type': 'pto'})
    client.simulate_put('/api/days/2026-10-30', json={'day_type': 'pto'})
    assert client.simulate_get('/api/reports/weeks/2026-W44').json['days_off'] == {'pto': 1}


@pytest.mark.parametrize('body, status', [
    (PART_TIME | {'valid_from': '2024-06-01'}, 409),
    (PART_TIME | {'work_days': []}, 422),
    (PART_TIME | {'work_days': ['Monday']}, 422),
    (PART_TIME | {'weekly_hours': '169:00'}, 422),
    (PART_TIME | {'weekly_hours': '30 hours'}, 422),
    (PART_TIME | {'state': 'Berlin'}, 422),
    (PART_TIME | {'state': 'Augsburg'}, 422),
])
def test_add_rejects_invalid_schedules(client, body, status):
    assert client.simulate_post('/api/work-schedules', json=body).status_code == status


def test_holidays_follow_the_state_and_company_rule_of_the_schedule(client):
    body = {'valid_from': '2027-01-01', 'weekly_hours': '40:00', 'work_days': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
            'state': 'BY', 'company_half_days': False}
    client.simulate_post('/api/work-schedules', json=body)
    epiphany = client.simulate_get('/api/days/2027-01-06').json  # Heilige Drei Könige: Bavaria, not Berlin
    assert (epiphany['day_type'], epiphany['holiday'], epiphany['target']) == ('public_holiday', 'Epiphany', '0:00')
    christmas_eve = client.simulate_get('/api/days/2027-12-24').json
    assert (christmas_eve['day_type'], christmas_eve['holiday'], christmas_eve['target']) == ('work', None, '8:00')
    women = client.simulate_get('/api/days/2026-03-09').json  # still Berlin before 2027: no holiday on a Monday
    assert women['day_type'] == 'work'


def test_only_schedule_cannot_be_deleted(client):
    [only] = client.simulate_get('/api/work-schedules').json
    assert client.simulate_delete(f'/api/work-schedules/{only["id"]}').status == falcon.HTTP_409


def test_schedules_are_documented(client):
    paths = client.simulate_get('/apidoc/openapi.json').json['paths']
    assert set(paths['/api/work-schedules']) == {'get', 'post'}
    assert set(paths['/api/work-schedules/{schedule_id}']) == {'get', 'put', 'delete'}
