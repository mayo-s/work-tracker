import falcon
import pytest
from falcon import testing

from src.app import create_app

SETUP = {
    'balance_start': '2027-03-01',
    'opening_balance': '+2:30',
    'schedule': {
        'weekly_hours': '32:00', 'work_days': ['Mon', 'Tue', 'Wed', 'Thu'], 'state': 'HH', 'company_half_days': False,
    },
    'pto_per_year': 30,
    'pto_first_year': 25,
    'services': [{'short_name': 'AUTH', 'name': 'auth-service'}],
    'user': {'username': 'pascal', 'email': 'turbo.pascal@example.com', 'first_name': 'Pascal', 'last_name': 'Turbo',
             'password': 'correct horse battery 9!'},
}


@pytest.fixture
def new(fresh_database):
    """A client on a new database, not set up yet."""
    return testing.TestClient(create_app(fresh_database))


def test_status(client, new):
    assert client.simulate_get('/api/setup').json == {'done': True}
    assert new.simulate_get('/api/setup').json == {'done': False}


@pytest.mark.parametrize('path', ['/', '/month', '/year', '/review', '/settings'])
def test_pages_forward_to_setup_until_it_is_done(new, path):
    result = new.simulate_get(path)
    assert (result.status, result.headers['location']) == (falcon.HTTP_303, '/setup')


def test_api_and_static_files_stay_reachable(new):
    assert new.simulate_get('/api/settings').status == falcon.HTTP_200
    assert new.simulate_get('/static/css/main.css').status == falcon.HTTP_200


def test_setup_page(new):
    result = new.simulate_get('/setup')
    assert result.status == falcon.HTTP_200
    assert 'data-page="setup"' in result.text


def test_setup_page_forwards_to_the_week_once_done(client):
    result = client.simulate_get('/setup')
    assert (result.status, result.headers['location']) == (falcon.HTTP_303, '/')


def test_setup_saves_everything_at_once(new):
    assert new.simulate_post('/api/setup', json=SETUP).json == {'done': True}
    assert new.simulate_get('/api/settings').json == {'balance_start': '2027-03-01', 'opening_balance': '2:30'}
    [schedule] = new.simulate_get('/api/work-schedules').json
    assert (schedule['valid_from'], schedule['daily_target'], schedule['state'], schedule['company_half_days']) == (
        '2027-03-01', '8:00', 'HH', False)
    assert [(year['year'], year['allowance']) for year in new.simulate_get('/api/pto-years').json] == [
        (2027, 25.0), (2028, 30.0)]
    assert [service['short_name'] for service in new.simulate_get('/api/services').json] == ['AUTH']
    assert new.simulate_get('/').status == falcon.HTTP_200


def test_setup_without_services(new):
    body = {key: value for key, value in SETUP.items() if key != 'services'}
    assert new.simulate_post('/api/setup', json=body).status == falcon.HTTP_200
    assert new.simulate_get('/api/services').json == []


def test_setup_is_refused_once_done(client):
    assert client.simulate_post('/api/setup', json=SETUP).status == falcon.HTTP_409


def test_duplicate_services_save_nothing(new):
    services = [{'short_name': 'AUTH'}, {'short_name': 'auth'}]
    assert new.simulate_post('/api/setup', json=SETUP | {'services': services}).status == falcon.HTTP_409
    assert new.simulate_get('/api/setup').json == {'done': False}
    assert new.simulate_get('/api/pto-years').json == []


@pytest.mark.parametrize('changes', [
    {'pto_first_year': -1},
    {'pto_first_year': 2.25},
    {'opening_balance': '1,5'},
    {'schedule': SETUP['schedule'] | {'work_days': []}},
    {'schedule': SETUP['schedule'] | {'state': 'XX'}},
    {'unknown': 1},
])
def test_setup_rejects_invalid_input(new, changes):
    assert new.simulate_post('/api/setup', json=SETUP | changes).status_code == 422


def test_setup_is_documented(client):
    assert set(client.simulate_get('/apidoc/openapi.json').json['paths']['/api/setup']) == {'get', 'post'}


def test_setup_creates_the_first_user_and_logs_in(fresh_database):
    client = testing.TestClient(create_app(fresh_database, auth=True))
    result = client.simulate_post('/api/setup', json=SETUP)
    assert 'wt_session' in result.cookies
    status = client.simulate_get('/api/auth/status', cookies={'wt_session': result.cookies['wt_session'].value}).json
    assert (status['has_users'], status['user']['username']) == (True, 'pascal')


def test_setup_needs_the_first_user(new):
    body = {key: value for key, value in SETUP.items() if key != 'user'}
    assert new.simulate_post('/api/setup', json=body).status == falcon.HTTP_409
    assert new.simulate_get('/api/setup').json == {'done': False}


def test_setup_keeps_an_existing_user(new):
    new.simulate_post('/api/auth/first-user', json=SETUP['user'])
    assert new.simulate_post('/api/setup', json=SETUP).status == falcon.HTTP_409
    body = {key: value for key, value in SETUP.items() if key != 'user'}
    assert new.simulate_post('/api/setup', json=body).status == falcon.HTTP_200
