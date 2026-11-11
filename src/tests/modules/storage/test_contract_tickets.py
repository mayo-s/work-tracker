"""Tickets: the same behaviour on SQLite and on DynamoDB (moto)."""

import datetime as dt

import pytest

from src.models.catalog import Ticket
from src.models.entries import Entry
from src.modules.storage.errors import ConflictError, NotFoundError


@pytest.fixture
def tickets(per_call, klara_id):
    return per_call(lambda store: store.tickets(klara_id))


def test_ensure_creates_ticket_without_service(tickets):
    assert tickets.get('ENGINE-461') is None
    assert tickets.ensure(' engine-461 ') == Ticket(key='ENGINE-461')
    assert tickets.get('ENGINE-461') == Ticket(key='ENGINE-461')


def test_ensure_keeps_existing_service(tickets, service_ids):
    tickets.ensure('ENGINE-461')
    tickets.set_service('ENGINE-461', service_ids['MSB'])
    assert tickets.ensure('engine-461').service_id == service_ids['MSB']


def test_all_sorted_by_prefix_and_number(tickets):
    for key in ('TNG-5214', 'KP-2035', 'TNG-999', 'ENGINE-461', 'TNG-10'):
        tickets.ensure(key)
    assert [ticket.key for ticket in tickets.all()] == ['ENGINE-461', 'KP-2035', 'TNG-10', 'TNG-999', 'TNG-5214']


def test_set_service_and_unset_it(tickets, service_ids):
    tickets.ensure('ENGINE-461')
    assert tickets.set_service('ENGINE-461', service_ids['MSB']).service_id == service_ids['MSB']
    assert tickets.get('ENGINE-461').service_id == service_ids['MSB']
    assert tickets.set_service('ENGINE-461', None).service_id is None


def test_set_service_of_missing_ticket(tickets, service_ids):
    with pytest.raises(NotFoundError):
        tickets.set_service('ENGINE-461', service_ids['MSB'])


def test_set_unknown_service(tickets):
    tickets.ensure('ENGINE-461')
    with pytest.raises(ConflictError):
        tickets.set_service('ENGINE-461', 404)


def test_assign_service_to_several_tickets(tickets, service_ids):
    for key in ('TNG-5214', 'AGA-39', 'AGA-40', 'AGA-41', 'KP-1951'):
        tickets.ensure(key)
    assert tickets.assign_service(['AGA-39', 'aga-40', 'AGA-41', 'AGA-39'], service_ids['HiS']) == 3
    assert [ticket.key for ticket in tickets.without_service()] == ['KP-1951', 'TNG-5214']


def test_assign_service_with_unknown_ticket_changes_nothing(tickets, service_ids):
    tickets.ensure('AGA-39')
    with pytest.raises(NotFoundError):
        tickets.assign_service(['AGA-39', 'AGA-404'], service_ids['HiS'])
    assert tickets.get('AGA-39').service_id is None


def test_entry_counts(tickets, per_call, klara_id):
    entries = per_call(lambda store: store.entries(klara_id))
    tickets.ensure('TNG-4138')
    for key in ('KP-1951', 'KP-1951', 'TNG-5214', None):
        entries.create(Entry(date=dt.date(2026, 1, 8), ticket_key=key, duration=60))
    assert tickets.entry_counts() == {'KP-1951': 2, 'TNG-5214': 1}


def test_a_service_for_more_tickets_than_one_transaction_holds(tickets, service_ids):
    keys = [f'AGA-{number}' for number in range(1, 151)]
    for key in keys:
        tickets.ensure(key)
    assert tickets.assign_service(keys, service_ids['HiS']) == 150
    assert tickets.without_service() == []
