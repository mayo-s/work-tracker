import pytest
from pydantic import ValidationError

from src.models.catalog import ActivityType, Service, Ticket


@pytest.mark.parametrize('key, stored', [
    ('ENGINE-461', 'ENGINE-461'),
    ('KP-2035', 'KP-2035'),
    ('MSI-2', 'MSI-2'),
    (' aga-39 ', 'AGA-39'),
])
def test_ticket_key(key, stored):
    assert Ticket(key=key).key == stored


@pytest.mark.parametrize('key', [
    '', 'ENGINE', '4138', '#4138', 'TNG 5212', 'TNG4840', 'MSI-02', 'TNG-2035ff', 'ENGINE-0', '-12',
])
def test_ticket_key_rejects_invalid(key):
    with pytest.raises(ValidationError):
        Ticket(key=key)


def test_service():
    service = Service(short_name=' MSB ', name='microsoft-bookings-service')
    assert service.short_name == 'MSB'
    assert Service(short_name='ImmoDrop').name == ''


@pytest.mark.parametrize('short_name', ['', '   '])
def test_service_rejects_empty_short_name(short_name):
    with pytest.raises(ValidationError):
        Service(short_name=short_name)


def test_activity_type_rejects_empty_name():
    with pytest.raises(ValidationError):
        ActivityType(name='')


def test_models_reject_unknown_fields():
    with pytest.raises(ValidationError):
        ActivityType(name='Travel', colour='blue')
