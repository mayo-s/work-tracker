import falcon
import pytest


LISTS = [
    ('/api/services', {'short_name': 'AUTH', 'name': 'auth-service'}, {'short_name': 'AUTH', 'name': 'authorizer'}),
    ('/api/activity-types', {'name': 'Incident'}, {'name': 'Incident handling', 'ticket_required': True}),
]


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
    response = client.simulate_post(path, json=body)
    assert response.status == falcon.HTTP_409
    assert response.json['description'].endswith(f'named "{next(iter(body.values()))}" already exists')


def test_the_id_is_not_chosen_by_the_client(client):
    assert client.simulate_post('/api/services', json={'short_name': 'AUTH', 'id': 7}).status_code == 422
