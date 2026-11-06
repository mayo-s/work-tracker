"""Managed lists (services, activity types) and tickets."""

import re
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field

from src.models.base import DomainModel, RecordId

TICKET_KEY_PATTERN = r'^[A-Z][A-Z0-9]*-[1-9]\d*$'


def _check_ticket_key(key: str) -> str:
    """The pattern with a message to show, e.g. on renaming a ticket (pydantic's would quote the pattern)."""
    if not re.fullmatch(TICKET_KEY_PATTERN, key):
        raise ValueError(f"Invalid ticket key '{key}': a project code, a dash and a number, e.g. TNG-4138")
    return key


TicketKey = Annotated[
    str,
    BeforeValidator(lambda value: value.strip().upper() if isinstance(value, str) else value),
    Field(max_length=30, description='Ticket key, e.g. ENGINE-461'),
    AfterValidator(_check_ticket_key),
]


class Service(DomainModel):
    id: RecordId | None = None
    short_name: str = Field(min_length=1, max_length=30, description='e.g. MSB')
    name: str = Field(default='', max_length=100, description='e.g. microsoft-bookings-service')


class ServiceChoice(Service):
    """A service to choose in an entry: a personal one, or one of the user's team (`team`: its name)."""

    team: str | None = None


class ActivityType(DomainModel):
    id: RecordId | None = None
    name: str = Field(min_length=1, max_length=50, description='e.g. Tool Management')
    ticket_required: bool = Field(default=False, description='An entry of this type needs a ticket, e.g. Coding')


CODING = 'Coding'  # the activity type of coding work; offered in the setup with tickets (SPEC 4.2)


def new_activity_type(name: str) -> ActivityType:
    """An activity type to add by name, e.g. by an import; Coding requires a ticket."""
    return ActivityType(name=name, ticket_required=name.casefold() == CODING.casefold())


class Ticket(DomainModel):
    """A ticket remembers its service; all entries of the ticket share it."""

    key: TicketKey
    service_id: RecordId | None = None
