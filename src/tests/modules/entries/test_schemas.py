import datetime as dt

import pytest
from pydantic import ValidationError

from src.models.entries import Entry
from src.modules.entries.schemas import EntryInput
from src.tests.ids import FIRST, SECOND

DATE = dt.date(2026, 10, 28)


def test_entry_input_on_a_ticket():
    data = EntryInput(date=DATE, activity_type_id=SECOND, duration='1:30', ticket_key='engine-597',
                      description=' permissions ')
    expected = Entry(id=FIRST, date=DATE, activity_type_id=SECOND, ticket_key='ENGINE-597', duration=90,
                     description='permissions')
    assert data.to_entry(FIRST) == expected
    assert not data.sets_service


def test_entry_input_with_service():
    assert EntryInput(date=DATE, activity_type_id=SECOND, duration='0:30', ticket_key='TNG-5882', service_id=None).sets_service


def test_entry_input_without_ticket():
    data = EntryInput(date=DATE, activity_type_id=SECOND, duration='4:00', ticket_key='', description='GCC')
    assert data.to_entry() == Entry(date=DATE, activity_type_id=SECOND, duration=240, description='GCC')


def test_a_service_needs_a_ticket():
    with pytest.raises(ValidationError, match='service_id needs a ticket_key'):
        EntryInput(date=DATE, activity_type_id=SECOND, duration='1:00', service_id=FIRST)
