"""User settings for balances and PTO."""

import datetime as dt
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from src.models.base import DomainModel

PtoDays = Annotated[Decimal, Field(ge=0, decimal_places=1)]


class Settings(DomainModel):
    balance_start: dt.date = Field(description='First day counted in the overtime balance')
    opening_balance: int = Field(default=0, description='Overtime in minutes before balance_start')
    pto_allowances: dict[int, PtoDays] = Field(description='PTO days per year, valid from that year on')
