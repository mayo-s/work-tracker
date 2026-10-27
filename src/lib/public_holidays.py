"""Berlin public holidays plus the company half days on Heiligabend and Silvester."""

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

import holidays

from src.lib.dates import each_day

_BERLIN = holidays.country_holidays('DE', subdiv='BE', language='en_US')
_COMPANY_HALF_DAYS = {(12, 24): "Christmas Eve", (12, 31): "New Year's Eve"}


class HolidayKind(StrEnum):
    PUBLIC = 'public'
    COMPANY_HALF_DAY = 'company_half_day'  # half PTO, half free by company policy


@dataclass(frozen=True)
class Holiday:
    date: dt.date
    name: str
    kind: HolidayKind


def holiday_on(date: dt.date) -> Holiday | None:
    """The public holiday or company half day on a date, if any (also on weekends)."""
    if name := _BERLIN.get(date):
        return Holiday(date, name, HolidayKind.PUBLIC)
    if name := _COMPANY_HALF_DAYS.get((date.month, date.day)):
        return Holiday(date, name, HolidayKind.COMPANY_HALF_DAY)
    return None


def holidays_between(start: dt.date, end: dt.date) -> list[Holiday]:
    """All holidays from start to end (inclusive), in date order."""
    return [found for day in each_day(start, end) if (found := holiday_on(day))]
