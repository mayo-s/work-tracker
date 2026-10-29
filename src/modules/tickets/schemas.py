"""API schemas for tickets."""

import sqlite3
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.models.catalog import Ticket, TicketKey
from src.modules.storage.catalog import ServiceRepository
from src.modules.storage.tickets import TicketRepository


class TicketView(BaseModel):
    key: str = Field(examples=['ENGINE-461'])
    service_id: int | None
    service: str | None = Field(description='Short name of the service')
    entries: int = Field(description='Number of entries of the ticket')


class TicketQuery(BaseModel):
    without_service: bool = Field(default=False, description='Only tickets without a service (for review)')


class TicketServiceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    service_id: int | None = Field(description='The service, or null to unassign it')


class ServiceAssignment(BaseModel):
    model_config = ConfigDict(extra='forbid')

    keys: list[TicketKey] = Field(min_length=1, examples=[['AGA-39', 'AGA-40']])
    service_id: int | None = Field(description='The service, or null to unassign it')


class AssignmentResult(BaseModel):
    assigned: int = Field(description='Number of distinct tickets changed')


class TicketRename(BaseModel):
    model_config = ConfigDict(extra='forbid')

    new_key: TicketKey = Field(description='New key; if it exists, both tickets are merged', examples=['KP-2035'])


class RenameView(BaseModel):
    ticket: TicketView
    action: Literal['renamed', 'merged']
    moved: int = Field(description='Number of entries moved to the new key')


def ticket_views(conn: sqlite3.Connection, user_id: str, tickets: Iterable[Ticket]) -> list[TicketView]:
    services = {service.id: service.short_name for service in ServiceRepository(conn, user_id).choices()}
    counts = TicketRepository(conn, user_id).entry_counts()
    return [
        TicketView(key=ticket.key, service_id=ticket.service_id, service=services.get(ticket.service_id),
                   entries=counts.get(ticket.key, 0))
        for ticket in tickets
    ]
