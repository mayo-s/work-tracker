import pytest
from pydantic import ValidationError

from src.models.catalog import Ticket
from src.modules.storage.catalog import ServiceRepository
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.tickets import TicketRepository


@pytest.fixture
def tickets(conn):
    return TicketRepository(conn)


@pytest.fixture
def service_ids(conn):
    return {service.short_name: service.id for service in ServiceRepository(conn).all()}


def test_get_missing_ticket(tickets):
    assert tickets.get('ENGINE-461') is None


def test_ensure_creates_ticket_without_service(tickets):
    assert tickets.ensure('ENGINE-461') == Ticket(key='ENGINE-461')
    assert tickets.get('ENGINE-461') == Ticket(key='ENGINE-461')


def test_ensure_keeps_existing_service(tickets, service_ids):
    tickets.ensure('ENGINE-461')
    tickets.set_service('ENGINE-461', service_ids['MSB'])
    assert tickets.ensure('engine-461').service_id == service_ids['MSB']


def test_keys_are_normalized(tickets):
    tickets.ensure(' aga-39 ')
    assert tickets.get('AGA-39').key == 'AGA-39'


def test_invalid_key(tickets):
    with pytest.raises(ValidationError):
        tickets.ensure('TNG4840')


def test_all_sorted_by_prefix_and_number(tickets):
    for key in ('TNG-5214', 'KP-2035', 'TNG-999', 'ENGINE-461', 'TNG-10'):
        tickets.ensure(key)
    assert [ticket.key for ticket in tickets.all()] == ['ENGINE-461', 'KP-2035', 'TNG-10', 'TNG-999', 'TNG-5214']


def test_set_service_remembers_service(tickets, service_ids):
    tickets.ensure('ENGINE-461')
    assert tickets.set_service('ENGINE-461', service_ids['MSB']).service_id == service_ids['MSB']
    assert tickets.get('ENGINE-461').service_id == service_ids['MSB']


def test_set_service_to_none(tickets, service_ids):
    tickets.ensure('ENGINE-461')
    tickets.set_service('ENGINE-461', service_ids['MSB'])
    assert tickets.set_service('ENGINE-461', None).service_id is None


def test_set_service_of_missing_ticket(tickets, service_ids):
    with pytest.raises(NotFoundError):
        tickets.set_service('ENGINE-461', service_ids['MSB'])


def test_set_unknown_service(tickets):
    tickets.ensure('ENGINE-461')
    with pytest.raises(ConflictError):
        tickets.set_service('ENGINE-461', 404)


def test_assign_service_to_several_tickets(tickets, service_ids):
    for key in ('AGA-39', 'AGA-40', 'AGA-41', 'TNG-5214'):
        tickets.ensure(key)
    assert tickets.assign_service(['AGA-39', 'aga-40', 'AGA-41', 'AGA-39'], service_ids['HiS']) == 3
    assert [ticket.key for ticket in tickets.without_service()] == ['TNG-5214']


def test_assign_service_with_unknown_ticket_changes_nothing(tickets, service_ids):
    tickets.ensure('AGA-39')
    with pytest.raises(NotFoundError):
        tickets.assign_service(['AGA-39', 'AGA-404'], service_ids['HiS'])
    assert tickets.get('AGA-39').service_id is None


def test_without_service(tickets, service_ids):
    for key in ('KP-1951', 'TNG-4138', 'ENGINE-461'):
        tickets.ensure(key)
    tickets.set_service('KP-1951', service_ids['ImmoDrop'])
    assert [ticket.key for ticket in tickets.without_service()] == ['ENGINE-461', 'TNG-4138']


def test_entry_counts(conn, tickets):
    tickets.ensure('TNG-4138')
    for key in ('KP-1951', 'KP-1951', 'TNG-5214'):
        tickets.ensure(key)
        conn.execute("INSERT INTO entries (date, kind, ticket_key, duration) VALUES ('2026-01-08', 'ticket', ?, 60)", (key,))
    conn.execute("INSERT INTO entries (date, kind, duration) VALUES ('2026-01-08', 'ticket', 60)")
    assert tickets.entry_counts() == {'KP-1951': 2, 'TNG-5214': 1}
