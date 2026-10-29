"""Public holidays of a German federal state, plus the company half days on Heiligabend and Silvester if they apply."""

import datetime as dt
import functools
from dataclasses import dataclass
from enum import StrEnum

import holidays

from src.lib.dates import each_day

# German federal states as `holidays` subdivisions, e.g. BE = Berlin, BY = Bayern, HH = Hamburg
STATES = ('BB', 'BE', 'BW', 'BY', 'HB', 'HE', 'HH', 'MV', 'NI', 'NW', 'RP', 'SH', 'SL', 'SN', 'ST', 'TH')
_COMPANY_HALF_DAYS = {(12, 24): "Christmas Eve", (12, 31): "New Year's Eve"}


@functools.cache
def _calendar(state: str) -> holidays.HolidayBase:
    return holidays.country_holidays('DE', subdiv=state, language='en_US')


@dataclass(frozen=True)
class HolidayRules:
    """The federal state whose public holidays apply, and whether 24.12. and 31.12. are company half days."""

    state: str = 'BE'
    company_half_days: bool = True

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(f'Unknown federal state {self.state!r}, expected one of {", ".join(STATES)}')


BERLIN = HolidayRules()


class HolidayKind(StrEnum):
    PUBLIC = 'public'
    COMPANY_HALF_DAY = 'company_half_day'  # half PTO, half free by company policy


@dataclass(frozen=True)
class Holiday:
    date: dt.date
    name: str
    kind: HolidayKind


def holiday_on(date: dt.date, rules: HolidayRules = BERLIN) -> Holiday | None:
    """The public holiday or company half day on a date, if any (also on weekends)."""
    if name := _calendar(rules.state).get(date):
        return Holiday(date, name, HolidayKind.PUBLIC)
    if rules.company_half_days and (name := _COMPANY_HALF_DAYS.get((date.month, date.day))):
        return Holiday(date, name, HolidayKind.COMPANY_HALF_DAY)
    return None


def holidays_between(start: dt.date, end: dt.date, rules: HolidayRules = BERLIN) -> list[Holiday]:
    """All holidays from start to end (inclusive), in date order."""
    return [found for day in each_day(start, end) if (found := holiday_on(day, rules))]
