import pytest

from src.models.catalog import ActivityType, Service
from src.modules.storage.catalog import ActivityTypeRepository, ServiceRepository
from src.modules.storage.errors import ConflictError, NotFoundError


@pytest.fixture
def services(conn):
    return ServiceRepository(conn)


@pytest.fixture
def activity_types(conn):
    return ActivityTypeRepository(conn)


def test_all_services_sorted_by_short_name(services):
    assert [service.short_name for service in services.all()] == ['HiS', 'ImmoDrop', 'MSB', 'O365', 'TTS']


def test_get_service(services):
    msb = next(service for service in services.all() if service.short_name == 'MSB')
    assert services.get(msb.id) == Service(id=msb.id, short_name='MSB', name='microsoft-bookings-service')


def test_get_missing_service(services):
    with pytest.raises(NotFoundError):
        services.get(404)


def test_add_service(services):
    added = services.add(Service(short_name='AUTH', name='auth-service'))
    assert added.id is not None
    assert services.get(added.id) == added


def test_add_duplicate_service_ignoring_case(services):
    duplicate = Service(short_name='msb')
    with pytest.raises(ConflictError):
        services.add(duplicate)


def test_update_service(services):
    added = services.add(Service(short_name='AUTH'))
    updated = services.update(added.model_copy(update={'name': 'auth-service'}))
    assert services.get(added.id) == updated


def test_update_missing_service(services):
    missing = Service(id=404, short_name='AUTH')
    with pytest.raises(NotFoundError):
        services.update(missing)


def test_update_service_to_duplicate_name(services):
    added = services.add(Service(short_name='AUTH'))
    renamed = added.model_copy(update={'short_name': 'TTS'})
    with pytest.raises(ConflictError):
        services.update(renamed)


def test_delete_service_unassigns_tickets(services, conn):
    added = services.add(Service(short_name='AUTH'))
    conn.execute("INSERT INTO tickets (key, service_id) VALUES ('AGA-39', ?)", (added.id,))
    services.delete(added.id)
    assert added.id not in [service.id for service in services.all()]
    assert conn.execute("SELECT service_id FROM tickets WHERE key = 'AGA-39'").fetchone()[0] is None


def test_delete_missing_service(services):
    with pytest.raises(NotFoundError):
        services.delete(404)


def test_all_activity_types_in_seed_order(activity_types):
    assert [activity.name for activity in activity_types.all()] == ['Tool Management', 'Meeting', 'Travel', 'Other']


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


def test_delete_activity_type_in_use(activity_types, conn):
    meeting = activity_types.all()[1]
    conn.execute(
        "INSERT INTO entries (date, kind, activity_type_id, duration) VALUES ('2026-10-26', 'activity', ?, 60)",
        (meeting.id,),
    )
    with pytest.raises(ConflictError):
        activity_types.delete(meeting.id)
