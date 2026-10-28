import falcon
import pytest

from src.modules.storage.catalog import ServiceRepository


@pytest.fixture
def service_ids(database):
    with database.transaction() as conn:
        return {service.short_name: service.id for service in ServiceRepository(conn).all()}


def add_entry(client, key, date='2026-03-02'):
    body = {'kind': 'ticket', 'date': date, 'duration': '1:00', 'ticket_key': key}
    assert client.simulate_post('/api/entries', json=body).status == falcon.HTTP_201


def test_list_tickets_with_entry_counts(client, service_ids):
    for key in ('TNG-5214', 'AGA-39', 'TNG-999', 'AGA-39'):
        add_entry(client, key)
    client.simulate_put('/api/tickets/AGA-39', json={'service_id': service_ids['HiS']})
    tickets = client.simulate_get('/api/tickets').json
    assert [(ticket['key'], ticket['entries'], ticket['service']) for ticket in tickets] == [
        ('AGA-39', 2, 'HiS'), ('TNG-999', 1, None), ('TNG-5214', 1, None),
    ]


def test_list_tickets_without_service(client, service_ids):
    add_entry(client, 'TNG-5214')
    add_entry(client, 'AGA-39')
    client.simulate_put('/api/tickets/AGA-39', json={'service_id': service_ids['HiS']})
    tickets = client.simulate_get('/api/tickets', params={'without_service': 'true'}).json
    assert [ticket['key'] for ticket in tickets] == ['TNG-5214']


def test_set_and_unassign_service(client, service_ids):
    add_entry(client, 'TNG-5214')
    assert client.simulate_put('/api/tickets/tng-5214', json={'service_id': service_ids['O365']}).json['service'] == 'O365'
    assert client.simulate_put('/api/tickets/TNG-5214', json={'service_id': None}).json['service'] is None


@pytest.mark.parametrize('key, body, status', [
    ('TNG-404', {'service_id': None}, falcon.HTTP_404),
    ('TNG-5214', {'service_id': 404}, falcon.HTTP_409),
])
def test_set_service_errors(client, key, body, status):
    add_entry(client, 'TNG-5214')
    assert client.simulate_put(f'/api/tickets/{key}', json=body).status == status


def test_assign_service_to_several_tickets(client, service_ids):
    for key in ('AGA-39', 'AGA-40', 'TNG-5214'):
        add_entry(client, key)
    body = {'keys': ['AGA-39', 'aga-40', 'AGA-39'], 'service_id': service_ids['HiS']}
    result = client.simulate_post('/api/tickets/assign-service', json=body)
    assert (result.status, result.json) == (falcon.HTTP_200, {'assigned': 2})
    assert [ticket['key'] for ticket in client.simulate_get('/api/tickets', params={'without_service': 'true'}).json] == [
        'TNG-5214']


def test_assign_service_with_unknown_ticket_changes_nothing(client, service_ids):
    add_entry(client, 'AGA-39')
    body = {'keys': ['AGA-39', 'AGA-404'], 'service_id': service_ids['HiS']}
    assert client.simulate_post('/api/tickets/assign-service', json=body).status == falcon.HTTP_404
    assert client.simulate_get('/api/tickets/AGA-39').json['service'] is None


@pytest.mark.parametrize('body', [{'keys': [], 'service_id': None}, {'keys': ['TNG4840'], 'service_id': None}])
def test_assign_service_rejects_invalid(client, body):
    assert client.simulate_post('/api/tickets/assign-service', json=body).status_code == 422


def test_rename_ticket(client, service_ids):
    add_entry(client, 'TNG-2035')
    client.simulate_put('/api/tickets/TNG-2035', json={'service_id': service_ids['ImmoDrop']})
    result = client.simulate_post('/api/tickets/TNG-2035/rename', json={'new_key': 'kp-2035'})
    assert result.status == falcon.HTTP_200
    assert result.json == {
        'ticket': {'key': 'KP-2035', 'service_id': service_ids['ImmoDrop'], 'service': 'ImmoDrop', 'entries': 1},
        'action': 'renamed',
        'moved': 1,
    }
    assert client.simulate_get('/api/tickets/TNG-2035').status == falcon.HTTP_404
    [entry] = client.simulate_get('/api/entries', params={'start': '2026-03-02', 'end': '2026-03-02'}).json
    assert (entry['ticket_key'], entry['changed']) == ('KP-2035', True)


def test_merge_into_existing_ticket(client, service_ids):
    add_entry(client, 'TNG-4347')
    add_entry(client, 'KP-1482')
    client.simulate_put('/api/tickets/KP-1482', json={'service_id': service_ids['HiS']})
    result = client.simulate_post('/api/tickets/TNG-4347/rename', json={'new_key': 'KP-1482'}).json
    assert (result['action'], result['moved'], result['ticket']['entries'], result['ticket']['service']) == (
        'merged', 1, 2, 'HiS')


@pytest.mark.parametrize('key, body, status', [
    ('TNG-404', {'new_key': 'KP-404'}, 404),
    ('TNG-2035', {'new_key': 'tng-2035'}, 409),
    ('TNG-2035', {'new_key': 'TNG-2035ff'}, 422),
])
def test_rename_errors(client, key, body, status):
    add_entry(client, 'TNG-2035')
    assert client.simulate_post(f'/api/tickets/{key}/rename', json=body).status_code == status
