import pytest
from pydantic import ValidationError

from src.models.catalog import ActivityType, Service, Ticket


def test_ticket_key_is_trimmed_and_upper_case():
    assert Ticket(key=' aga-39 ').key == 'AGA-39'


@pytest.mark.parametrize('key', ['ENGINE', '#4138', 'TNG 5212', 'TNG4840', 'MSI-02', 'TNG-2035ff', 'ENGINE-0'])
def test_ticket_key_rejects_invalid(key):
    with pytest.raises(ValidationError):
        Ticket(key=key)


def test_service_short_name_is_trimmed():
    assert Service(short_name=' MSB ').short_name == 'MSB'


def test_service_rejects_blank_short_name():
    with pytest.raises(ValidationError):
        Service(short_name='   ')


def test_models_reject_unknown_fields():
    with pytest.raises(ValidationError):
        ActivityType(name='Travel', colour='blue')
