import datetime as dt

import pytest
from pydantic import ValidationError

from src.lib.balances import DayRecord
from src.lib.daytypes import DayType
from src.lib.durations import parse_clock, parse_duration
from src.models.days import Day

DATE = dt.date(2026, 10, 26)


def test_day_without_times():
    day = Day(date=DATE, day_type=DayType.PTO)
    assert day.worked == 0
    assert day.to_record() == DayRecord(0, DayType.PTO)


def test_day_with_legal_break():
    day = Day(date=DATE, start=parse_clock('08:15'), end=parse_clock('17:00'))
    assert day.worked == parse_duration('8:15')
    assert day.to_record() == DayRecord(parse_duration('8:15'), None)


def test_day_with_explicit_break():
    day = Day(date=DATE, start=parse_clock('08:30'), end=parse_clock('20:00'), break_minutes=180)
    assert day.worked == parse_duration('8:30')


def test_day_with_explicit_zero_break():
    day = Day(date=DATE, start=parse_clock('07:30'), end=parse_clock('16:00'), break_minutes=0)
    assert day.worked == parse_duration('8:30')


def test_day_strips_note():
    assert Day(date=DATE, note='  Anreise LÜBECK ').note == 'Anreise LÜBECK'


@pytest.mark.parametrize('times', [
    {'start': 480},
    {'end': 960},
    {'break_minutes': 30},
    {'start': 960, 'end': 480},
    {'start': 480, 'end': 720, 'break_minutes': 241},
    {'start': -1, 'end': 480},
    {'start': 480, 'end': 1440},
    {'start': 480, 'end': 960, 'break_minutes': -5},
])
def test_day_rejects_invalid_times(times):
    with pytest.raises(ValidationError):
        Day(date=DATE, **times)


def test_day_validates_assignment():
    day = Day(date=DATE, start=parse_clock('08:00'), end=parse_clock('16:00'))
    with pytest.raises(ValidationError):
        day.end = parse_clock('07:00')
