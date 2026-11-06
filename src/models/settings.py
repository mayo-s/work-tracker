"""User settings: the overtime balance and the way of working."""

import datetime as dt
from typing import Literal

from pydantic import Field

from src.models.base import DomainModel

WorkMode = Literal['developer', 'tickets', 'activities', 'times']


class Settings(DomainModel):
    balance_start: dt.date = Field(description='First day counted in the overtime balance')
    opening_balance: int = Field(default=0, description='Overtime in minutes before balance_start')
    work_mode: WorkMode = Field(default='developer', description='Way of working: developer, tickets (no coding), '
                                'activities (only) or times (only); it shapes the pages, not the data')
