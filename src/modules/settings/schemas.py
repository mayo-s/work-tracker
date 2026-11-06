"""Settings as shown and entered in the API: the opening balance as signed h:mm, and the way of working."""

import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from src.lib.durations import format_duration, parse_signed_duration
from src.models.settings import Settings, WorkMode
from src.modules.storage.settings import Theme
from src.utils.api import SignedDurationText


class SettingsView(BaseModel):
    model_config = ConfigDict(extra='forbid')

    balance_start: dt.date = Field(description='First day counted in the overtime balance', examples=['2024-06-01'])
    opening_balance: SignedDurationText = Field(
        description='Overtime before the start day, e.g. 12:30, -1:45, 1.5 or -2h; answered as h:mm',
    )
    work_mode: WorkMode

    @classmethod
    def of(cls, settings: Settings) -> Self:
        return cls(balance_start=settings.balance_start, opening_balance=format_duration(settings.opening_balance),
                   work_mode=settings.work_mode)

    def to_settings(self) -> Settings:
        return Settings(balance_start=self.balance_start, opening_balance=parse_signed_duration(self.opening_balance),
                        work_mode=self.work_mode)


class ThemeView(BaseModel):
    model_config = ConfigDict(extra='forbid')

    theme: Theme = Field(description='Color theme: system follows the system setting, or light / dark')
