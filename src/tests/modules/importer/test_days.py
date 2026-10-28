import datetime as dt

import pytest

from src.lib.daytypes import DayType
from src.lib.durations import parse_clock, parse_duration
from src.models.review import FlagReason
from src.modules.importer.days import classify_day
from src.modules.importer.sheet import SheetRow


def row(date, start='', end='', pause=None, total='0:00', *comment):
    return SheetRow(
        date=date,
        start=parse_clock(start) if start else None,
        end=parse_clock(end) if end else None,
        pause=pause,
        total=parse_duration(total),
        comment=comment,
    )


def times(imported):
    day = imported.day
    return day.start, day.end, day.break_minutes


def test_empty_future_row():
    assert classify_day(row(dt.date(2026, 11, 2))) is None


def test_work_day_keeps_times_and_lines():
    imported = classify_day(row(dt.date(2026, 1, 9), '07:30', '16:00', 30, '8:00', '3,0 KP-1951: data mapping'))
    assert imported.day.day_type is None
    assert times(imported) == (parse_clock('07:30'), parse_clock('16:00'), 30)
    assert imported.day.worked == parse_duration('8:00')
    assert imported.lines == ('3,0 KP-1951: data mapping',)
    assert imported.flags == ()


def test_empty_pause_is_an_explicit_zero_break():
    imported = classify_day(row(dt.date(2026, 9, 11), '07:30', '16:00', None, '8:30'))
    assert imported.day.break_minutes == 0
    assert imported.day.worked == parse_duration('8:30')


def test_work_day_with_placeholder_times_is_real_work():
    imported = classify_day(row(dt.date(2025, 12, 5), '08:00', '16:00', None, '8:00', 'H4CKathon MCP'))
    assert imported.day.worked == parse_duration('8:00')
    assert imported.lines == ('H4CKathon MCP',)


@pytest.mark.parametrize('comment, total, day_type', [
    ('PTO', '8:00', DayType.PTO),
    ('8,0 PTO', '8:00', DayType.PTO),
    ('PTO', '0:00', DayType.OVERTIME_OFF),
    ('Off sick', '8:00', DayType.SICK),
    ('PTO (off sick)', '8:00', DayType.SICK),
])
def test_full_day_off_ignores_placeholder_times(comment, total, day_type):
    imported = classify_day(row(dt.date(2025, 5, 30), '08:00', '16:00', 480 if total == '0:00' else None, total, comment))
    assert imported.day.day_type is day_type
    assert times(imported) == (None, None, None)
    assert imported.lines == ()


@pytest.mark.parametrize('date, start, end, pause, total, comment, day_type, new_end', [
    (dt.date(2024, 6, 20), '07:15', '16:00', 0, '8:45', '4,0 PTO (afternoon)', DayType.PTO_HALF, '12:00'),
    (dt.date(2024, 11, 1), '08:00', '16:00', None, '8:00', '4,0 PTO (12:00 - 16:00)', DayType.PTO_HALF, '12:00'),
    (dt.date(2025, 12, 12), '08:30', '16:30', None, '8:00', '0,5 PTO', DayType.PTO_HALF, '12:30'),
    (dt.date(2025, 1, 30), '08:30', '17:00', 30, '8:00', '4,0 off sick afternoon', DayType.SICK_HALF, '13:00'),
    (dt.date(2025, 5, 13), '07:15', '16:00', 30, '8:15', '4,0 PTO (off sick)', DayType.SICK_HALF, '12:00'),
])
def test_half_day_moves_end_back(date, start, end, pause, total, comment, day_type, new_end):
    imported = classify_day(row(date, start, end, pause, total, comment))
    assert imported.day.day_type is day_type
    assert imported.day.end == parse_clock(new_end)
    assert imported.lines == ()


def test_half_day_keeps_other_lines():
    imported = classify_day(
        row(dt.date(2024, 6, 20), '07:15', '16:00', 0, '8:45', 'Start 7:15 End 12:00', '2,0 #4095', '4,0 PTO (afternoon)')
    )
    assert imported.lines == ('Start 7:15 End 12:00', '2,0 #4095')
    assert imported.day.worked == parse_duration('4:45')


@pytest.mark.parametrize('date, start, end, pause, total, comment', [
    (dt.date(2025, 3, 17), '08:15', '16:45', 30, '8:00', '2,0 PTO Zahnarzt'),
    (dt.date(2025, 2, 25), '11:00', '16:00', 0, '5:00', '3,0 PTO TTU'),
    (dt.date(2025, 5, 7), '11:30', '16:00', 30, '4:00', '4,0 PTO (Wohnungsbesichtigung)'),
])
def test_overtime_used_becomes_note(date, start, end, pause, total, comment):
    imported = classify_day(row(date, start, end, pause, total, comment, '1,5 Meeting: Planning'))
    assert imported.day.day_type is None
    assert imported.day.note == comment
    assert imported.day.worked == parse_duration(total)
    assert imported.lines == ('1,5 Meeting: Planning',)


@pytest.mark.parametrize('date, comment', [
    (dt.date(2026, 1, 1), 'New Years Day'),
    (dt.date(2025, 5, 8), 'Public Holiday (80th anniversary of the liberation from National Socialism, Berlin only)'),
    (dt.date(2024, 12, 24), 'PTO'),
    (dt.date(2025, 12, 31), '0,5 PTO / Silvester'),
])
def test_holiday_and_company_half_day_are_automatic(date, comment):
    imported = classify_day(row(date, '08:00', '16:00', None, '8:00', comment))
    assert imported.day.day_type is None
    assert imported.day.worked == 0
    assert imported.lines == ()


def test_weekend_placeholder_is_ignored():
    imported = classify_day(row(dt.date(2026, 1, 3), '08:00', '16:00', None, '8:00'))
    assert imported.day.worked == 0
    assert imported.flags == ()


def test_weekend_pto_and_notes():
    pto = classify_day(row(dt.date(2026, 7, 11), '08:00', '16:00', None, '8:00', 'PTO'))
    first_day = classify_day(row(dt.date(2024, 6, 1), '08:00', '16:00', 0, '8:00', 'First Day at Dr. Klein'))
    assert (pto.lines, pto.flags) == ((), ())
    assert (first_day.lines, first_day.flags) == (('First Day at Dr. Klein',), ())


def test_weekend_work_is_sum_minus_eight_hours_and_flagged():
    imported = classify_day(row(dt.date(2025, 12, 6), '08:00', '19:30', None, '11:30', '3,5 ABREISE Lübeck'))
    assert times(imported) == (parse_clock('08:00'), parse_clock('11:30'), 0)
    assert imported.day.worked == parse_duration('3:30')
    [flag] = imported.flags
    assert (flag.date, flag.reason) == (dt.date(2025, 12, 6), FlagReason.WEEKEND_HOURS)
    assert flag.detail == '08:00–19:30, Sum 11:30: 3,5 ABREISE Lübeck'


def test_weekend_hours_not_counted_by_sheet_are_flagged():
    comment = '5,0 Secretary - Holacracy Constitution'
    imported = classify_day(row(dt.date(2024, 11, 9), '08:00', '16:00', None, '8:00', comment))
    assert imported.day.worked == 0
    assert imported.lines == ('5,0 Secretary - Holacracy Constitution',)
    assert [flag.reason for flag in imported.flags] == [FlagReason.WEEKEND_HOURS]


def test_planned_pto_without_times():
    imported = classify_day(row(dt.date(2026, 12, 28), '', '', None, '0:00', 'PTO'))
    assert imported.day.day_type is DayType.PTO
    assert times(imported) == (None, None, None)


def test_future_holiday_label():
    imported = classify_day(row(dt.date(2026, 12, 24), '', '', None, '0:00', 'Heiligabend'))
    assert (imported.day.worked, imported.lines) == (0, ())
