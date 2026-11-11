import datetime as dt

from src.lib.daytypes import DayType
from src.lib.stays import Stays
from src.models.days import Day
from src.modules.days.schemas import DayInput, day_view, team_view_day


def test_day_input_to_day():
    day = DayInput(start='7:15', end='16:00', break_time='0:30', note=' OFFICE DAY ').to_day(dt.date(2026, 10, 28))
    assert day == Day(date=dt.date(2026, 10, 28), start=435, end=960, break_minutes=30, note='OFFICE DAY')


def test_view_of_unrecorded_work_day():
    view = day_view(dt.date(2026, 10, 29), None)
    assert (view.weekday, view.day_type, view.automatic, view.recorded) == ('Thu', DayType.WORK, True, False)
    assert (view.start, view.break_time, view.worked, view.target, view.overtime) == (None, None, '0:00', '8:00',
                                                                                      '-8:00')


def test_view_with_legal_break():
    view = day_view(dt.date(2026, 10, 28), Day(date=dt.date(2026, 10, 28), start=435, end=960))
    assert (view.start, view.end, view.break_time, view.break_default) == ('07:15', '16:00', '0:30', True)
    assert (view.worked, view.overtime) == ('8:15', '0:15')


def test_view_of_open_day():
    date = dt.date(2026, 10, 28)
    view = day_view(date, Day(date=date, start=492))
    assert (view.start, view.end, view.best_end) == ('08:12', None, '16:42')
    assert (view.break_time, view.break_default, view.worked, view.overtime) == (None, False, '0:00', '-8:00')
    assert day_view(date, Day(date=date, start=492, break_minutes=60)).best_end == '17:12'
    saturday = dt.date(2026, 10, 31)
    assert day_view(saturday, Day(date=saturday, start=492)).best_end is None  # no target
    assert day_view(date, Day(date=date, start=492, end=990)).best_end is None


def test_team_view_shows_nothing_of_an_open_day_outside_the_stay():
    date = dt.date(2026, 10, 28)
    outside = team_view_day(day_view(date, Day(date=date, start=492)), Stays(((dt.date(2026, 11, 2), None),)))
    assert (outside.start, outside.best_end) == (None, None)


def test_view_of_holiday_and_half_pto():
    assert day_view(dt.date(2026, 12, 24), None).holiday == 'Christmas Eve'
    half = day_view(dt.date(2026, 4, 30), Day(date=dt.date(2026, 4, 30), day_type=DayType.PTO_HALF, start=420, end=660,
                                              break_minutes=0))
    assert (half.day_type, half.automatic, half.target, half.overtime, half.pto_days) == (
        DayType.PTO_HALF, False, '4:00', '0:00', 0.5)
