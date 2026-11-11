import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.tests.helpers import session

SETUP = {
    'balance_start': '2027-03-01',
    'opening_balance': '+2:30',
    'schedule': {
        'weekly_hours': '32:00', 'work_days': ['Mon', 'Tue', 'Wed', 'Thu'], 'state': 'HH', 'company_half_days': False,
    },
    'pto_per_year': 30,
    'pto_first_year': 25,
    'services': [{'short_name': 'AUTH', 'name': 'auth-service'}],
    'work_mode': 'tickets',
}
ROOT = {'username': 'rainer', 'email': 'rainer.zufall@example.com', 'first_name': 'Rainer', 'last_name': 'Zufall',
        'password': 'correct horse battery 9!'}
PASCAL = {'username': 'pascal', 'email': 'turbo.pascal@example.com', 'first_name': 'Pascal', 'last_name': 'Turbo',
          'password': 'correct horse battery 9!'}


@pytest.fixture
def new(fresh_database):
    """A client on a new database, not set up yet."""
    return testing.TestClient(create_app(fresh_database))


def test_status(client, new):
    assert client.simulate_get('/api/setup').json == {'done': True}
    assert new.simulate_get('/api/setup').json == {'done': False}


def test_pages_forward_to_setup_until_it_is_done(new):
    result = new.simulate_get('/settings')
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
    assert new.simulate_get('/api/settings').json == {
        'balance_start': '2027-03-01', 'opening_balance': '2:30', 'work_mode': 'tickets'}
    [schedule] = new.simulate_get('/api/work-schedules').json
    assert (schedule['valid_from'], schedule['daily_target'], schedule['state'], schedule['company_half_days']) == (
        '2027-03-01', '8:00', 'HH', False)
    assert [(year['year'], year['allowance']) for year in new.simulate_get('/api/pto-years').json] == [
        (2027, 25.0), (2028, 30.0)]
    assert [service['short_name'] for service in new.simulate_get('/api/services').json] == ['AUTH']
    assert new.simulate_get('/api/activity-types').json[-1] | {'id': None} == {
        'id': None, 'name': 'Coding', 'ticket_required': True}  # with tickets, asked for by default
    assert new.simulate_get('/').status == falcon.HTTP_200


@pytest.mark.parametrize('changes', [{'coding': False}, {'work_mode': 'activities'}])
def test_coding_only_with_tickets_and_when_asked_for(new, changes):
    new.simulate_post('/api/setup', json=SETUP | changes)
    assert 'Coding' not in [kind['name'] for kind in new.simulate_get('/api/activity-types').json]


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
])
def test_setup_rejects_invalid_input(new, changes):
    assert new.simulate_post('/api/setup', json=SETUP | changes).status_code == 422


@pytest.fixture
def with_login(fresh_database):
    """A client on a new database with the login on."""
    return testing.TestClient(create_app(fresh_database, auth=True))


def test_a_new_database_creates_root_first(with_login):
    result = with_login.simulate_get('/week')
    assert (result.status, result.headers['location']) == (falcon.HTTP_303, '/setup')
    assert with_login.simulate_post('/api/setup', json=SETUP).status == falcon.HTTP_401  # nobody to set up yet
    root = with_login.simulate_post('/api/auth/root', json=ROOT)
    assert (root.status, root.json['role']) == (falcon.HTTP_201, 'root')
    status = with_login.simulate_get('/api/auth/status', cookies=session(root)).json
    assert (status['has_root'], status['user']['username']) == (True, 'rainer')


def test_users_set_up_their_own_data_after_registering(with_login):
    root = session(with_login.simulate_post('/api/auth/root', json=ROOT))
    with_login.simulate_put('/api/admin/settings', cookies=root, json={'registration': True})
    pascal = session(with_login.simulate_post('/api/auth/register', json=PASCAL))
    assert with_login.simulate_get('/week', cookies=pascal).headers['location'] == '/setup'
    assert with_login.simulate_post('/api/setup', cookies=pascal, json=SETUP).json == {'done': True}
    assert with_login.simulate_get('/week', cookies=pascal).status == falcon.HTTP_200


def test_the_setup_takes_no_account(new):
    assert new.simulate_post('/api/setup', json=SETUP | {'user': PASCAL}).status_code == 422
