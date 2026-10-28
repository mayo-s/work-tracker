"""Tickets endpoints: /api/tickets/{key}, used to pre-fill the service of a known ticket."""

import falcon
from pydantic import BaseModel, Field, ValidationError
from spectree import Response

from src.modules.storage.catalog import ServiceRepository
from src.modules.storage.database import Database
from src.modules.storage.tickets import TicketRepository
from src.utils.spec import spec

TAGS = ['Tickets']


class TicketView(BaseModel):
    key: str = Field(examples=['ENGINE-461'])
    service_id: int | None
    service: str | None = Field(description='Short name of the service')


class TicketItem:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response('HTTP_404', HTTP_200=TicketView), tags=TAGS,
                   path_parameter_descriptions={'key': 'Ticket key, e.g. ENGINE-461 (case-insensitive)'})
    def on_get(self, req: falcon.Request, resp: falcon.Response, key: str) -> None:
        """A known ticket with the service it remembers."""
        with self._database.transaction() as conn:
            try:
                ticket = TicketRepository(conn).get(key)
            except ValidationError:
                ticket = None
            if ticket is None:
                raise falcon.HTTPNotFound(description=f'Unknown ticket {key}')
            services = {service.id: service.short_name for service in ServiceRepository(conn).all()}
        resp.media = TicketView(key=ticket.key, service_id=ticket.service_id, service=services.get(ticket.service_id))
