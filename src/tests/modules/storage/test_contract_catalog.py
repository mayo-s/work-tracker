"""Services and activity types: the same behaviour on SQLite and on DynamoDB (moto)."""

import datetime as dt

import pytest

from src.models.catalog import ActivityType, Service
from src.models.entries import ActivityEntry
from src.modules.storage.errors import ConflictError, NotFoundError


@pytest.fixture
def services(per_call, klara_id, service_ids):
    return per_call(lambda store: store.services(klara_id))


@pytest.fixture
def activity_types(per_call, klara_id):
    return per_call(lambda store: store.activity_types(klara_id))


@pytest.fixture
def tickets(per_call, klara_id):
    return per_call(lambda store: store.tickets(klara_id))


def test_all_services_sorted_by_short_name(services):
    assert [service.short_name for service in services.all()] == ['HiS', 'ImmoDrop', 'MSB', 'O365', 'TTS']


def test_get_service(services):
    msb = next(service for service in services.all() if service.short_name == 'MSB')
    assert services.get(msb.id) == Service(id=msb.id, short_name='MSB', name='microsoft-bookings-service')


def test_missing_service(services):
    with pytest.raises(NotFoundError):
        services.get(404)
    with pytest.raises(NotFoundError):
        services.update(Service(id=404, short_name='AUTH'))
    with pytest.raises(NotFoundError):
        services.delete(404)


def test_add_and_update_service(services):
    added = services.add(Service(short_name='AUTH'))
    assert services.get(added.id) == added
    updated = services.update(added.model_copy(update={'name': 'auth-service'}))
    assert services.get(added.id) == updated


def test_short_names_are_unique_ignoring_case(services):
    added = services.add(Service(short_name='AUTH'))
    with pytest.raises(ConflictError):
        services.add(Service(short_name='msb'))
    with pytest.raises(ConflictError):
        services.update(added.model_copy(update={'short_name': 'tts'}))


def test_delete_service_unassigns_tickets(services, tickets):
    added = services.add(Service(short_name='AUTH'))
    tickets.ensure('AGA-39')
    tickets.set_service('AGA-39', added.id)
    services.delete(added.id)
    assert added.id not in [service.id for service in services.all()]
    assert tickets.get('AGA-39').service_id is None


def test_deleted_and_renamed_services_free_their_names(services):
    services.delete(services.add(Service(short_name='AUTH')).id)
    renamed = services.add(Service(short_name='auth'))
    services.update(renamed.model_copy(update={'short_name': 'IAM'}))
    assert services.add(Service(short_name='AUTH')).short_name == 'AUTH'


def test_add_rename_and_delete_activity_type(activity_types):
    added = activity_types.add(ActivityType(name='Incident'))
    renamed = activity_types.update(added.model_copy(update={'name': 'Incident handling'}))
    assert activity_types.get(added.id) == renamed
    activity_types.delete(added.id)
    assert 'Incident handling' not in [activity.name for activity in activity_types.all()]


def test_add_duplicate_activity_type(activity_types):
    duplicate = ActivityType(name='travel')
    with pytest.raises(ConflictError):
        activity_types.add(duplicate)


def test_delete_activity_type_in_use(activity_types, per_call, klara_id):
    meeting = activity_types.all()[1]
    per_call(lambda store: store.entries(klara_id)).create(
        ActivityEntry(date=dt.date(2026, 10, 26), activity_type_id=meeting.id, duration=60))
    with pytest.raises(ConflictError, match='used by entries'):
        activity_types.delete(meeting.id)


def test_activity_types_in_the_order_they_were_created(activity_types):
    activity_types.add(ActivityType(name='Incident'))
    assert [kind.name for kind in activity_types.all()] == ['Tool Management', 'Meeting', 'Travel', 'Other', 'Incident']
