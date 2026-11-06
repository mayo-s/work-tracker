"""User settings: the overtime balance and the way of working."""

import datetime as dt
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from src.models.base import DomainModel


def _former_way(value: object) -> object:
    """The former way of working "Developer" is now "Tickets and activities" (TASKS.md L.10); stored settings and
    export files with it still read."""
    return 'tickets' if value == 'developer' else value


WorkMode = Annotated[
    Literal['tickets', 'activities', 'times'], BeforeValidator(_former_way),
    Field(description='Way of working: tickets (and activities), activities (only) or times (only); it shapes the pages, '
                      'not the data'),
]


class Settings(DomainModel):
    balance_start: dt.date = Field(description='First day counted in the overtime balance')
    opening_balance: int = Field(default=0, description='Overtime in minutes before balance_start')
    work_mode: WorkMode = 'tickets'
