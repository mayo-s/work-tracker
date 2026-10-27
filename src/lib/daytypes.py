"""Day types and their effect on target time, PTO and overtime of a single day."""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import NamedTuple

from src.lib.public_holidays import HolidayKind, holiday_on

FULL_DAY = 8 * 60
HALF_DAY = FULL_DAY // 2


class DayType(StrEnum):
    WORK = 'work'
    PTO = 'pto'
    PTO_HALF = 'pto_half'
    SICK = 'sick'
    SICK_HALF = 'sick_half'
    OVERTIME_OFF = 'overtime_off'
    UNPAID_LEAVE = 'unpaid_leave'
    PUBLIC_HOLIDAY = 'public_holiday'
    COMPANY_HALF_DAY = 'company_half_day'


class _Rule(NamedTuple):
    target: int
    pto_days: Decimal


# Target and PTO used on a weekday; on weekends every type has target 0 and uses no PTO.
_RULES = {
    DayType.WORK: _Rule(FULL_DAY, Decimal(0)),
    DayType.PTO: _Rule(0, Decimal(1)),
    DayType.PTO_HALF: _Rule(HALF_DAY, Decimal('0.5')),
    DayType.SICK: _Rule(0, Decimal(0)),
    DayType.SICK_HALF: _Rule(HALF_DAY, Decimal(0)),
    DayType.OVERTIME_OFF: _Rule(FULL_DAY, Decimal(0)),
    DayType.UNPAID_LEAVE: _Rule(0, Decimal(0)),
    DayType.PUBLIC_HOLIDAY: _Rule(0, Decimal(0)),
    DayType.COMPANY_HALF_DAY: _Rule(0, Decimal('0.5')),
}
_HOLIDAY_TYPES = {HolidayKind.PUBLIC: DayType.PUBLIC_HOLIDAY, HolidayKind.COMPANY_HALF_DAY: DayType.COMPANY_HALF_DAY}


@dataclass(frozen=True)
class DaySummary:
    date: dt.date
    day_type: DayType
    target: int
    worked: int
    pto_days: Decimal

    @property
    def overtime(self) -> int:
        return self.worked - self.target


def is_weekend(date: dt.date) -> bool:
    return date.weekday() >= 5


def automatic_day_type(date: dt.date) -> DayType:
    """Public holiday or company half day from the Berlin calendar, otherwise work."""
    found = holiday_on(date)
    return _HOLIDAY_TYPES[found.kind] if found else DayType.WORK


def summarize_day(date: dt.date, worked: int = 0, day_type: DayType | None = None) -> DaySummary:
    """Target, PTO used and overtime of a day; a chosen day type overrides the automatic one."""
    if worked < 0:
        raise ValueError('worked must not be negative')
    resolved = day_type or automatic_day_type(date)
    rule = _Rule(0, Decimal(0)) if is_weekend(date) else _RULES[resolved]
    return DaySummary(date, resolved, rule.target, worked, rule.pto_days)
