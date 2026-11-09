import datetime as dt

import pytest
from pydantic import ValidationError

from src.models.entries import Entry

DATE = dt.date(2026, 10, 26)


def test_entry_on_a_ticket():
    entry = Entry(date=DATE, ticket_key='engine-597', duration=90, description=' europace permissions ')
    assert (entry.ticket_key, entry.description) == ('ENGINE-597', 'europace permissions')


def test_a_former_entry_may_wait_for_its_activity_type():
    assert Entry(date=DATE, ticket_key='TNG-1', duration=60).activity_type_id is None


@pytest.mark.parametrize('duration', [-15, 1455])
def test_duration_rejects_invalid(duration):
    with pytest.raises(ValidationError):
        Entry(date=DATE, ticket_key='KP-1951', duration=duration)
