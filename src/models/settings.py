"""User settings for the overtime balance."""

import datetime as dt

from pydantic import Field

from src.models.base import DomainModel


class Settings(DomainModel):
    balance_start: dt.date = Field(description='First day counted in the overtime balance')
    opening_balance: int = Field(default=0, description='Overtime in minutes before balance_start')
