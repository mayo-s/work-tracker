import falcon
import pytest

LISTS = [
    ('/api/services', {'short_name': 'AUTH', 'name': 'auth-service'}, {'short_name': 'AUTH', 'name': 'authorizer'}),
    ('/api/activity-types', {'name': 'Incident'}, {'name': 'Incident handling'}),
]


def test_seeded_services(client):
    assert [service['short_name'] for service in client.simulate_get('/api/services').json] == [
        'HiS', 'ImmoDrop', 'MSB', 'O365', 'TTS']


def test_seeded_activity_types(client):
    assert [activity['name'] for activity in client.simulate_get('/api/activity-types').json] == [
        'Tool Management', 'Meeting', 'Travel', 'Other']


@pytest.mark.parametrize('path, body, changed', LISTS)
def test_create_read_update_delete(client, path, body, changed):
    created = client.simulate_post(path, json=body)
    assert created.status == falcon.HTTP_201
    item_path = f'{path}/{created.json["id"]}'
    assert created.headers['location'] == item_path
    assert client.simulate_get(item_path).json == created.json
    assert client.simulate_put(item_path, json=changed).json == {'id': created.json['id']} | changed
    assert client.simulate_delete(item_path).status == falcon.HTTP_204
    assert client.simulate_get(item_path).status == falcon.HTTP_404


@pytest.mark.parametrize('path, body', [
    ('/api/services', {'short_name': 'msb'}),
    ('/api/activity-types', {'name': 'travel'}),
])
def test_duplicate_name(client, path, body):
    assert client.simulate_post(path, json=body).status == falcon.HTTP_409


@pytest.mark.parametrize('path, body', [
    ('/api/services', {'short_name': ''}),
    ('/api/services', {'short_name': 'AUTH', 'id': 7}),
    ('/api/activity-types', {}),
])
def test_invalid_input(client, path, body):
    assert client.simulate_post(path, json=body).status_code == 422


@pytest.mark.parametrize('path', ['/api/services/404', '/api/activity-types/404'])
def test_missing_record(client, path):
    assert client.simulate_get(path).status == falcon.HTTP_404
    body = {'short_name': 'X'} if 'services' in path else {'name': 'X'}
    assert client.simulate_put(path, json=body).status == falcon.HTTP_404
    assert client.simulate_delete(path).status == falcon.HTTP_404


def test_activity_type_in_use_cannot_be_deleted(client):
    meeting = next(activity for activity in client.simulate_get('/api/activity-types').json if activity['name'] == 'Meeting')
    body = {'kind': 'activity', 'date': '2026-10-28', 'duration': '1:00', 'activity_type_id': meeting['id']}
    client.simulate_post('/api/entries', json=body)
    assert client.simulate_delete(f'/api/activity-types/{meeting["id"]}').status == falcon.HTTP_409


def test_deleting_a_service_unassigns_its_tickets(client):
    service = client.simulate_post('/api/services', json={'short_name': 'AUTH'}).json
    body = {'kind': 'ticket', 'date': '2026-10-28', 'duration': '1:00', 'ticket_key': 'AGA-39', 'service_id': service['id']}
    client.simulate_post('/api/entries', json=body)
    client.simulate_delete(f'/api/services/{service["id"]}')
    assert client.simulate_get('/api/tickets/AGA-39').json['service_id'] is None
