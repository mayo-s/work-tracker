import pytest

from src.lib.durations import parse_clock, parse_duration
from src.lib.worktime import best_end, legal_break, presence_time, worked_time


def test_presence_time():
    assert presence_time(parse_clock('07:30'), parse_clock('22:15')) == parse_duration('14:45')
    assert presence_time(parse_clock('08:15'), parse_clock('08:15')) == 0


def test_presence_time_rejects_end_before_start():
    start, end = parse_clock('16:00'), parse_clock('08:00')
    with pytest.raises(ValueError):
        presence_time(start, end)


@pytest.mark.parametrize('presence, expected', [
    ('6:00', '0:00'),
    ('6:01', '0:01'),  # the break never takes worked time below 6:00
    ('6:30', '0:30'),
    ('9:30', '0:30'),
    ('9:31', '0:31'),  # nor below 9:00
    ('9:45', '0:45'),
    ('14:45', '0:45'),
])
def test_legal_break(presence, expected):
    assert legal_break(parse_duration(presence)) == parse_duration(expected)


def test_legal_break_rejects_negative_presence():
    with pytest.raises(ValueError):
        legal_break(-1)


@pytest.mark.parametrize('start, end, break_time, worked', [
    ('08:15', '17:00', None, '8:15'),  # the legal break
    ('08:30', '20:00', '3:00', '8:30'),  # a longer break
    ('07:30', '16:00', '0:00', '8:30'),  # no break taken
])
def test_worked_time(start, end, break_time, worked):
    break_minutes = None if break_time is None else parse_duration(break_time)
    assert worked_time(parse_clock(start), parse_clock(end), break_minutes) == parse_duration(worked)


@pytest.mark.parametrize('break_minutes', [-1, 241])
def test_worked_time_rejects_invalid_break(break_minutes):
    start, end = parse_clock('08:00'), parse_clock('12:00')
    with pytest.raises(ValueError):
        worked_time(start, end, break_minutes)


@pytest.mark.parametrize('target, break_minutes, end', [
    ('6:00', None, '14:00'),  # no legal break up to 6 h of work
    ('6:01', None, '14:31'),
    ('8:00', None, '16:30'),
    ('9:00', None, '17:30'),
    ('9:01', None, '17:46'),
    ('8:00', 60, '17:00'),  # the entered break
    ('8:00', 0, '16:00'),
])
def test_best_end_meets_the_target(target, break_minutes, end):
    start = parse_clock('08:00')
    assert best_end(start, parse_duration(target), break_minutes) == parse_clock(end)
    assert worked_time(start, parse_clock(end), break_minutes) == parse_duration(target)


def test_no_best_end_without_a_target_or_past_midnight():
    assert best_end(parse_clock('08:00'), 0) is None
    assert best_end(parse_clock('16:00'), parse_duration('8:00')) is None
