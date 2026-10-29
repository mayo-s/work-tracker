import pytest

from src.lib.durations import (
    TimeFormatError,
    format_clock,
    format_duration,
    is_quarter_hour,
    parse_clock,
    parse_decimal_hours,
    parse_duration,
    parse_signed_duration,
    split_evenly,
)


@pytest.mark.parametrize('text, minutes', [
    ('00:00', 0),
    ('08:15', 495),
    ('7:15', 435),
    (' 16:00 ', 960),
    ('23:59', 1439),
])
def test_parse_clock(text, minutes):
    assert parse_clock(text) == minutes


@pytest.mark.parametrize('text', ['', '8', '08:5', '0815', '24:00', '12:60', '-1:00', '08:15:00', 'ab:cd'])
def test_parse_clock_rejects_invalid(text):
    with pytest.raises(TimeFormatError):
        parse_clock(text)


@pytest.mark.parametrize('minutes, text', [(0, '00:00'), (495, '08:15'), (1439, '23:59')])
def test_format_clock(minutes, text):
    assert format_clock(minutes) == text


@pytest.mark.parametrize('minutes', [-1, 1440])
def test_format_clock_rejects_out_of_range(minutes):
    with pytest.raises(ValueError):
        format_clock(minutes)


@pytest.mark.parametrize('text, minutes', [
    ('0:00', 0),
    ('0:45', 45),
    ('1:30', 90),
    ('12:45', 765),
    ('25:00', 1500),
    (' 2:15 ', 135),
])
def test_parse_duration(text, minutes):
    assert parse_duration(text) == minutes


@pytest.mark.parametrize('text', ['', '1', '1:5', '1:60', '-1:30', '1,5', ':30'])
def test_parse_duration_rejects_invalid(text):
    with pytest.raises(TimeFormatError):
        parse_duration(text)


@pytest.mark.parametrize('text, minutes', [('12:30', 750), ('+12:30', 750), (' -1:45 ', -105), ('-0:00', 0)])
def test_parse_signed_duration(text, minutes):
    assert parse_signed_duration(text) == minutes


@pytest.mark.parametrize('text', ['', '-', '+-1:00', '--1:00', '1,5'])
def test_parse_signed_duration_rejects_invalid(text):
    with pytest.raises(TimeFormatError):
        parse_signed_duration(text)


@pytest.mark.parametrize('minutes, text', [
    (0, '0:00'),
    (45, '0:45'),
    (90, '1:30'),
    (1500, '25:00'),
    (-105, '-1:45'),
    (-15, '-0:15'),
])
def test_format_duration(minutes, text):
    assert format_duration(minutes) == text


@pytest.mark.parametrize('text, minutes', [
    ('8', 480),
    ('1,5', 90),
    ('0,75', 45),
    ('0,5', 30),
    ('1.25', 75),
    ('2,0', 120),
    (' 4,0 ', 240),
])
def test_parse_decimal_hours(text, minutes):
    assert parse_decimal_hours(text) == minutes


@pytest.mark.parametrize('text', ['', ',5', '1,', '1,5h', '-1', '1:30', '0,333'])
def test_parse_decimal_hours_rejects_invalid(text):
    with pytest.raises(TimeFormatError):
        parse_decimal_hours(text)


@pytest.mark.parametrize('minutes, expected', [(0, True), (15, True), (90, True), (20, False), (-15, True)])
def test_is_quarter_hour(minutes, expected):
    assert is_quarter_hour(minutes) is expected


@pytest.mark.parametrize('total, parts, shares', [
    (180, 1, [180]),
    (180, 2, [90, 90]),
    (90, 4, [30, 30, 15, 15]),
    (60, 3, [30, 15, 15]),
    (480, 4, [120, 120, 120, 120]),
    (30, 4, [15, 15, 0, 0]),
    (50, 2, [35, 15]),
    (0, 2, [0, 0]),
])
def test_split_evenly(total, parts, shares):
    assert split_evenly(total, parts) == shares


@pytest.mark.parametrize('total, parts', [(60, 0), (-15, 2)])
def test_split_evenly_rejects_invalid(total, parts):
    with pytest.raises(ValueError):
        split_evenly(total, parts)
