import datetime as dt

import pytest
from pydantic import ValidationError

from src.models.entries import ActivityEntry, TicketEntry
from src.modules.entries.schemas import EntryInput

DATE = dt.date(2026, 10, 28)


def test_ticket_entry_input():
    data = EntryInput(kind='ticket', date=DATE, duration='1:30', ticket_key='engine-597', description=' permissions ')
    assert data.to_entry(7) == TicketEntry(id=7, date=DATE, ticket_key='ENGINE-597', duration=90, description='permissions')
    assert not data.sets_service


def test_ticket_entry_input_with_service():
    assert EntryInput(kind='ticket', date=DATE, duration='0:30', ticket_key='TNG-5882', service_id=None).sets_service


def test_activity_entry_input():
    data = EntryInput(kind='activity', date=DATE, duration='4:00', activity_type_id=1, note='GCC')
    assert data.to_entry() == ActivityEntry(date=DATE, activity_type_id=1, duration=240, note='GCC')
    assert not data.sets_service


@pytest.mark.parametrize('data', [
    {'kind': 'ticket', 'duration': '1:30'},
    {'kind': 'ticket', 'duration': '1:30', 'ticket_key': 'ENGINE-597', 'activity_type_id': 1},
    {'kind': 'ticket', 'duration': '1:30', 'ticket_key': 'ENGINE-597', 'note': 'x'},
    {'kind': 'ticket', 'duration': '1:30', 'ticket_key': 'TNG4840'},
    {'kind': 'ticket', 'duration': '1:20', 'ticket_key': 'ENGINE-597'},
    {'kind': 'ticket', 'duration': '1,5', 'ticket_key': 'ENGINE-597'},
    {'kind': 'activity', 'duration': '1:00'},
    {'kind': 'activity', 'duration': '1:00', 'activity_type_id': 1, 'ticket_key': 'ENGINE-597'},
    {'kind': 'activity', 'duration': '1:00', 'activity_type_id': 1, 'service_id': 2},
    {'kind': 'activity', 'duration': '1:00', 'activity_type_id': 1, 'coding': True},
    {'kind': 'meeting', 'duration': '1:00'},
    {'kind': 'ticket', 'duration': '1:00', 'ticket_key': 'ENGINE-597', 'hours': 1},
])
def test_entry_input_rejects_invalid(data):
    with pytest.raises(ValidationError):
        EntryInput(date=DATE, **data)
