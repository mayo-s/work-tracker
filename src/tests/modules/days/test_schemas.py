import datetime as dt

import pytest
from pydantic import ValidationError

from src.lib.daytypes import DayType
from src.models.days import Day
from src.models.review import FlagReason, ReviewFlag
from src.modules.days.schemas import DayInput, day_view


def test_day_input_to_day():
    day = DayInput(start='7:15', end='16:00', break_time='0:30', note=' OFFICE DAY ').to_day(dt.date(2026, 10, 28))
    assert day == Day(date=dt.date(2026, 10, 28), start=435, end=960, break_minutes=30, note='OFFICE DAY')


def test_day_input_normalizes_times():
    assert DayInput(start='7:15', end='16:00', break_time='0:30').start == '07:15'


@pytest.mark.parametrize('data', [
    {'start': '08:00'},
    {'start': '16:00', 'end': '08:00'},
    {'start': '08:00', 'end': '12:00', 'break_time': '5:00'},
    {'start': '8.00', 'end': '16:00'},
    {'break_time': '0:30'},
    {'day_type': 'holiday'},
    {'note': 'x', 'colour': 'blue'},
])
def test_day_input_rejects_invalid(data):
    with pytest.raises(ValidationError):
        DayInput(**data)


def test_view_of_unrecorded_work_day():
    view = day_view(dt.date(2026, 10, 29), None, [])
    assert (view.weekday, view.day_type, view.automatic, view.recorded) == ('Thu', DayType.WORK, True, False)
    assert (view.start, view.break_time, view.worked, view.target, view.overtime) == (None, None, '0:00', '8:00',
                                                                                      '-8:00')


def test_view_with_legal_break():
    view = day_view(dt.date(2026, 10, 28), Day(date=dt.date(2026, 10, 28), start=435, end=960), [])
    assert (view.start, view.end, view.break_time, view.break_default) == ('07:15', '16:00', '0:30', True)
    assert (view.worked, view.overtime) == ('8:15', '0:15')


def test_view_of_holiday_and_half_pto():
    assert day_view(dt.date(2026, 12, 24), None, []).holiday == 'Christmas Eve'
    half = day_view(dt.date(2026, 4, 30), Day(date=dt.date(2026, 4, 30), day_type=DayType.PTO_HALF, start=420, end=660,
                                              break_minutes=0), [])
    assert (half.day_type, half.automatic, half.target, half.overtime, half.pto_days) == (
        DayType.PTO_HALF, False, '4:00', '0:00', 0.5)


def test_view_with_flags():
    flag = ReviewFlag(id=7, date=dt.date(2025, 12, 6), reason=FlagReason.WEEKEND_HOURS, detail='3,5 ABREISE Lübeck')
    view = day_view(dt.date(2025, 12, 6), None, [flag])
    expected = [(7, FlagReason.WEEKEND_HOURS, '3,5 ABREISE Lübeck')]
    assert [(item.id, item.reason, item.detail) for item in view.flags] == expected
