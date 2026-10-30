"""SQLite only, until the tickets repository runs on DynamoDB too: entries create their tickets."""

import datetime as dt

import pytest

from src.models.entries import TicketEntry
from src.modules.storage.entries import EntryRepository
from src.modules.storage.tickets import TicketRepository
from src.tests.users import USER

MONDAY = dt.date(2026, 10, 26)


@pytest.fixture
def entries(conn):
    return EntryRepository(conn, USER)


@pytest.fixture
def ticket_entry():
    return TicketEntry(date=MONDAY, ticket_key='ENGINE-597', duration=90, description='europace permissions', coding=True)


def test_create_ticket_entry_creates_ticket(entries, conn, ticket_entry):
    entries.create(ticket_entry)
    assert TicketRepository(conn, USER).get('ENGINE-597') is not None


def test_update_to_new_ticket_creates_ticket(entries, conn, ticket_entry):
    created = entries.create(ticket_entry)
    entries.update(created.model_copy(update={'ticket_key': 'ENGINE-598'}))
    assert TicketRepository(conn, USER).get('ENGINE-598') is not None
    assert entries.history(created.id)[-1].changes == {'ticket_key': ('ENGINE-597', 'ENGINE-598')}


def test_split_creates_the_tickets(entries, conn):
    entry = entries.create(TicketEntry(date=MONDAY, ticket_key='TNG-4347', duration=360))
    entries.split(entry.id, ['tng-4347', 'KP-1482'])
    assert TicketRepository(conn, USER).get('KP-1482') is not None
