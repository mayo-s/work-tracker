import datetime as dt

import pytest
from pydantic import ValidationError

from src.models.entries import TicketEntry

DATE = dt.date(2026, 10, 26)


def test_ticket_entry():
    entry = TicketEntry(date=DATE, ticket_key='engine-597', duration=90, description=' europace permissions ')
    assert (entry.ticket_key, entry.description, entry.coding) == ('ENGINE-597', 'europace permissions', False)


def test_ticket_entry_without_ticket_for_review():
    assert TicketEntry(date=DATE, duration=360, description='PR reviews zipkin lib', coding=True).ticket_key is None


@pytest.mark.parametrize('duration', [-15, 10, 1455])
def test_duration_rejects_invalid(duration):
    with pytest.raises(ValidationError):
        TicketEntry(date=DATE, ticket_key='KP-1951', duration=duration)
