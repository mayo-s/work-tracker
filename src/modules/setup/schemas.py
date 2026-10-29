"""The initial setup of a new database: everything entered on /setup, saved at once."""

import datetime as dt
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.models.catalog import Service
from src.modules.auth.schemas import NewUserInput
from src.models.pto import PtoDays, PtoYear
from src.models.settings import Settings
from src.modules.catalog.resources import ServiceInput
from src.modules.schedules.schemas import ScheduleTerms
from src.lib.durations import parse_signed_duration
from src.utils.api import SignedDurationText

Days = Annotated[PtoDays, Field(ge=0)]


class SetupInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    balance_start: dt.date = Field(description='First day counted, e.g. the first day at a new job')
    opening_balance: SignedDurationText = Field(default='0:00', description='Overtime taken over, h:mm')
    schedule: ScheduleTerms = Field(description='The work schedule from the first day on')
    pto_per_year: Days = Field(default=Decimal(30), description='PTO days per year, entered for the year after the first')
    pto_first_year: Days = Field(description='PTO days of the first year, e.g. pro rata')
    services: list[ServiceInput] = Field(default=[], description='Services of the job; more can be added later')
    user: NewUserInput | None = Field(default=None, description='The first user, who is logged in afterwards')

    def settings(self) -> Settings:
        return Settings(balance_start=self.balance_start, opening_balance=parse_signed_duration(self.opening_balance))

    def pto_years(self) -> list[PtoYear]:
        year = self.balance_start.year
        return [PtoYear(year=year, allowance=self.pto_first_year), PtoYear(year=year + 1, allowance=self.pto_per_year)]

    def service_models(self) -> list[Service]:
        return [Service(**service.model_dump()) for service in self.services]


class SetupStatus(BaseModel):
    done: bool = Field(description='False for a new database until the setup is finished')
