"""Managed lists (services, activity types) and tickets."""

from typing import Annotated

from pydantic import BeforeValidator, Field

from src.models.base import DomainModel

TICKET_KEY_PATTERN = r'^[A-Z][A-Z0-9]*-[1-9]\d*$'

TicketKey = Annotated[
    str,
    BeforeValidator(lambda value: value.strip().upper() if isinstance(value, str) else value),
    Field(pattern=TICKET_KEY_PATTERN, max_length=30, description='Ticket key, e.g. ENGINE-461'),
]


class Service(DomainModel):
    id: int | None = None
    short_name: str = Field(min_length=1, max_length=30, description='e.g. MSB')
    name: str = Field(default='', max_length=100, description='e.g. microsoft-bookings-service')


class ActivityType(DomainModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=50, description='e.g. Tool Management')


class Ticket(DomainModel):
    """A ticket remembers its service; all entries of the ticket share it."""

    key: TicketKey
    service_id: int | None = None
