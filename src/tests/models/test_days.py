import datetime as dt

import pytest
from pydantic import ValidationError

from src.lib.balances import DayRecord
from src.lib.daytypes import DayType
from src.lib.durations import parse_clock, parse_duration
from src.models.days import Day

DATE = dt.date(2026, 10, 26)


def test_day_without_times():
    assert Day(date=DATE, day_type=DayType.PTO).to_record() == DayRecord(0, DayType.PTO)


def test_day_with_legal_break():
    day = Day(date=DATE, start=parse_clock('08:15'), end=parse_clock('17:00'), note='  Anreise LÜBECK ')
    assert (day.worked, day.note) == (parse_duration('8:15'), 'Anreise LÜBECK')
    assert day.to_record() == DayRecord(parse_duration('8:15'), None)


@pytest.mark.parametrize('times', [
    {'start': 480},
    {'break_minutes': 30},
    {'start': 960, 'end': 480},
    {'start': 480, 'end': 720, 'break_minutes': 241},
])
def test_day_rejects_invalid_times(times):
    with pytest.raises(ValidationError):
        Day(date=DATE, **times)
