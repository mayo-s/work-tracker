import datetime as dt

import pytest
from pydantic import TypeAdapter, ValidationError

from src.models.entries import ActivityEntry, Entry, TicketEntry

DATE = dt.date(2026, 10, 26)
ENTRY = TypeAdapter(Entry)


def test_ticket_entry():
    entry = TicketEntry(date=DATE, ticket_key='engine-597', duration=90, description=' europace permissions ')
    assert entry.ticket_key == 'ENGINE-597'
    assert entry.description == 'europace permissions'
    assert entry.coding is False


def test_ticket_entry_without_ticket_for_review():
    assert TicketEntry(date=DATE, duration=360, description='PR reviews zipkin lib', coding=True).ticket_key is None


def test_activity_entry():
    entry = ActivityEntry(date=DATE, activity_type_id=1, duration=120, note='GCC Tactical')
    assert entry.kind == 'activity'


@pytest.mark.parametrize('duration', [0, 15, 45, 1440])
def test_duration_in_quarter_hours(duration):
    assert TicketEntry(date=DATE, ticket_key='KP-1951', duration=duration).duration == duration


@pytest.mark.parametrize('duration', [-15, 10, 50, 1455])
def test_duration_rejects_invalid(duration):
    with pytest.raises(ValidationError):
        TicketEntry(date=DATE, ticket_key='KP-1951', duration=duration)


@pytest.mark.parametrize('data, model', [
    ({'kind': 'ticket', 'date': '2026-10-26', 'ticket_key': 'TNG-5214', 'duration': 240}, TicketEntry),
    ({'kind': 'activity', 'date': '2026-10-26', 'activity_type_id': 2, 'duration': 60}, ActivityEntry),
])
def test_entry_union_picks_kind(data, model):
    assert isinstance(ENTRY.validate_python(data), model)


@pytest.mark.parametrize('data', [
    {'kind': 'meeting', 'date': '2026-10-26', 'duration': 60},
    {'kind': 'activity', 'date': '2026-10-26', 'ticket_key': 'TNG-5214', 'duration': 60},
    {'date': '2026-10-26', 'ticket_key': 'TNG-5214', 'duration': 60},
])
def test_entry_union_rejects_invalid(data):
    with pytest.raises(ValidationError):
        ENTRY.validate_python(data)
