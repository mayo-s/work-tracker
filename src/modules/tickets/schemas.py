"""API schemas for tickets."""

from collections.abc import Iterable
from functools import cached_property
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.models.catalog import Ticket, TicketKey
from src.modules.storage.store import Store


class TicketView(BaseModel):
    key: str = Field(examples=['ENGINE-461'])
    service_id: str | None
    service: str | None = Field(description='Short name of the service')
    entries: int = Field(description='Number of entries of the ticket')


class TicketQuery(BaseModel):
    without_service: bool = Field(default=False, description='Only tickets without a service (for review)')


class TicketServiceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    service_id: str | None = Field(description='The service, or null to unassign it')


class ServiceAssignment(BaseModel):
    model_config = ConfigDict(extra='forbid')

    keys: list[TicketKey] = Field(min_length=1, examples=[['AGA-39', 'AGA-40']])
    service_id: str | None = Field(description='The service, or null to unassign it')


class AssignmentResult(BaseModel):
    assigned: int = Field(description='Number of distinct tickets changed')


class TicketRename(BaseModel):
    model_config = ConfigDict(extra='forbid')

    new_key: TicketKey = Field(description='New key; if it exists, both tickets are merged', examples=['KP-2035'])


class RenameView(BaseModel):
    ticket: TicketView
    action: Literal['renamed', 'merged']
    moved: int = Field(description='Number of entries moved to the new key')


class TicketServices:
    """The service of a user's tickets, which their entries have, and the short names of the services they choose
    from (their own and their team's); within the transaction of the given store."""

    def __init__(self, store: Store, user_id: str) -> None:
        self._tickets = store.tickets(user_id)
        self._names = {service.id: service.short_name for service in store.services(user_id).choices()}

    @cached_property
    def _by_ticket(self) -> dict[str, str | None]:
        return {ticket.key: ticket.service_id for ticket in self._tickets.all()}

    def of_ticket(self, key: str | None) -> str | None:
        return self._by_ticket.get(key)

    def name(self, service_id: str | None) -> str | None:
        return self._names.get(service_id)


def ticket_views(store: Store, user_id: str, tickets: Iterable[Ticket]) -> list[TicketView]:
    services = TicketServices(store, user_id)
    counts = store.tickets(user_id).entry_counts()
    return [
        TicketView(key=ticket.key, service_id=ticket.service_id, service=services.name(ticket.service_id),
                   entries=counts.get(ticket.key, 0))
        for ticket in tickets
    ]
