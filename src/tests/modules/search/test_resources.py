import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.catalog import ActivityTypeRepository, ServiceRepository
from src.tests.users import USER

TODAY = dt.date(2026, 10, 28)


@pytest.fixture
def client(database):
    return testing.TestClient(create_app(database, today=lambda: TODAY))


@pytest.fixture
def ids(database):
    """Klara's services and activity types by name."""
    with database.transaction() as conn:
        services = {service.short_name: service.id for service in ServiceRepository(conn, USER).all()}
        return services | {kind.name: kind.id for kind in ActivityTypeRepository(conn, USER).all()}


@pytest.fixture
def entries(client, ids):
    """Europace work this year and last year, and other work."""
    for date, key, duration, description, service in (
            ('2025-12-01', 'ENGINE-594', '1:00', 'europace credentials', 'MSB'),
            ('2026-03-02', 'ENGINE-590', '2:00', 'service id', 'MSB'),
            ('2026-10-05', 'ENGINE-594', '3:00', 'Europace credentials', 'MSB'),
            ('2026-10-06', 'ENGINE-597', '1:00', 'europace permissions', None)):
        body = {'kind': 'ticket', 'date': date, 'duration': duration, 'ticket_key': key, 'description': description,
                'service_id': ids.get(service)}
        assert client.simulate_post('/api/entries', json=body).status == falcon.HTTP_201
    body = {'kind': 'activity', 'date': '2026-09-07', 'duration': '0:30', 'activity_type_id': ids['Meeting'],
            'note': 'Europace jour fixe'}
    assert client.simulate_post('/api/entries', json=body).status == falcon.HTTP_201


def found(client, **params):
    result = client.simulate_get('/api/search', params=params)
    assert result.status == falcon.HTTP_200
    return result.json


def test_every_word_matches_a_ticket_key_start_or_the_text(client, entries):
    result = found(client, text='engine-59 EUROPACE')
    assert (result['start'], result['end'], result['duration'], result['count']) == ('2026-01-01', '2026-12-31', '4:00', 2)
    assert result['groups'] == [{'kind': 'ticket', 'key': 'ENGINE-594', 'duration': '3:00', 'entries': 1},
                                {'kind': 'ticket', 'key': 'ENGINE-597', 'duration': '1:00', 'entries': 1}]
    assert result['months'] == [{'month': '2026-10', 'duration': '4:00', 'entries': 2}]
    assert [(entry['date'], entry['ticket_key']) for entry in result['entries']] == [
        ('2026-10-06', 'ENGINE-597'), ('2026-10-05', 'ENGINE-594')]  # newest first


def test_without_text_all_entries_of_the_period(client, entries):
    result = found(client, start='2025-12-01', end='2026-03-31')
    assert result['groups'] == [{'kind': 'ticket', 'key': 'ENGINE-590', 'duration': '2:00', 'entries': 1},
                                {'kind': 'ticket', 'key': 'ENGINE-594', 'duration': '1:00', 'entries': 1}]
    assert [month['month'] for month in result['months']] == ['2025-12', '2026-03']


def test_service_or_activity_type_narrow_the_search(client, entries, ids):
    def keys(**params):
        return [group['key'] for group in found(client, text='europace', **params)['groups']]

    assert keys() == ['ENGINE-594', 'ENGINE-597', 'Meeting']
    assert keys(service_id=ids['MSB']) == ['ENGINE-594']
    assert keys(service_id='none') == ['ENGINE-597']
    assert keys(activity_type_id=ids['Meeting']) == ['Meeting']


def test_end_before_start(client):
    assert client.simulate_get('/api/search', params={'start': '2026-10-01', 'end': '2026-09-30'}).status_code == 422
