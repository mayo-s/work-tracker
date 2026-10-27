import pytest

from src.lib.durations import parse_clock, parse_duration
from src.lib.worktime import legal_break, presence_time, worked_time


@pytest.mark.parametrize('start, end, presence', [
    ('08:00', '16:00', '8:00'),
    ('08:15', '08:15', '0:00'),
    ('07:30', '22:15', '14:45'),
])
def test_presence_time(start, end, presence):
    assert presence_time(parse_clock(start), parse_clock(end)) == parse_duration(presence)


def test_presence_time_rejects_end_before_start():
    start, end = parse_clock('16:00'), parse_clock('08:00')
    with pytest.raises(ValueError):
        presence_time(start, end)


@pytest.mark.parametrize('presence, expected', [
    ('0:00', '0:00'),
    ('4:15', '0:00'),
    ('6:00', '0:00'),
    ('6:01', '0:01'),
    ('6:15', '0:15'),
    ('6:30', '0:30'),
    ('6:45', '0:30'),
    ('8:30', '0:30'),
    ('9:30', '0:30'),
    ('9:31', '0:31'),
    ('9:40', '0:40'),
    ('9:45', '0:45'),
    ('10:00', '0:45'),
    ('14:45', '0:45'),
])
def test_legal_break(presence, expected):
    assert legal_break(parse_duration(presence)) == parse_duration(expected)


@pytest.mark.parametrize('presence', range(0, 16 * 60, 5))
def test_legal_break_keeps_worked_time_within_limits(presence):
    worked = presence - legal_break(presence)
    assert worked <= 6 * 60 or legal_break(presence) >= 30
    assert worked <= 9 * 60 or legal_break(presence) == 45


def test_legal_break_rejects_negative_presence():
    with pytest.raises(ValueError):
        legal_break(-1)


@pytest.mark.parametrize('start, end, break_time, worked', [
    ('08:15', '17:00', None, '8:15'),
    ('07:30', '16:00', None, '8:00'),
    ('08:30', '15:45', None, '6:45'),
    ('09:00', '15:00', None, '6:00'),
    ('09:00', '15:20', None, '6:00'),
    ('08:00', '17:40', None, '9:00'),
    ('07:15', '18:00', None, '10:00'),
    ('08:30', '20:00', '3:00', '8:30'),
    ('07:30', '16:00', '0:00', '8:30'),
    ('08:00', '12:00', '0:45', '3:15'),
])
def test_worked_time(start, end, break_time, worked):
    break_minutes = None if break_time is None else parse_duration(break_time)
    assert worked_time(parse_clock(start), parse_clock(end), break_minutes) == parse_duration(worked)


@pytest.mark.parametrize('break_minutes', [-1, 241])
def test_worked_time_rejects_invalid_break(break_minutes):
    start, end = parse_clock('08:00'), parse_clock('12:00')
    with pytest.raises(ValueError):
        worked_time(start, end, break_minutes)
