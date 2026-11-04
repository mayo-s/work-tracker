import pytest

from src.lib.durations import (
    TimeFormatError,
    format_clock,
    format_duration,
    is_quarter_hour,
    parse_clock,
    parse_decimal_hours,
    parse_duration,
    parse_hours_minutes,
    parse_signed_duration,
    split_evenly,
)


@pytest.mark.parametrize('text, minutes', [('00:00', 0), ('7:15', 435), (' 16:00 ', 960), ('23:59', 1439)])
def test_parse_clock(text, minutes):
    assert parse_clock(text) == minutes


@pytest.mark.parametrize('text', ['', '08:5', '0815', '24:00', '12:60', '-1:00', '08:15:00'])
def test_parse_clock_rejects_invalid(text):
    with pytest.raises(TimeFormatError):
        parse_clock(text)


def test_format_clock():
    assert (format_clock(0), format_clock(495), format_clock(1439)) == ('00:00', '08:15', '23:59')


@pytest.mark.parametrize('minutes', [-1, 1440])
def test_format_clock_rejects_out_of_range(minutes):
    with pytest.raises(ValueError):
        format_clock(minutes)


@pytest.mark.parametrize('text, minutes', [
    ('0:45', 45),
    ('25:00', 1500),
    (' 2:15 ', 135),
    ('1.5', 90),
    ('1,5', 90),
    ('2', 120),
    ('1h30m', 90),
    ('1h30', 90),
    ('1.5h', 90),
    ('1 H 30 Min', 90),
    ('90m', 90),
])
def test_parse_duration(text, minutes):
    assert parse_duration(text) == minutes


@pytest.mark.parametrize('text', ['', '1:5', '1:60', '-1:30', '1.01', '30s', '1h60m', '1.5h30m', '1m30', '1:30h'])
def test_parse_duration_rejects_invalid(text):
    with pytest.raises(TimeFormatError):
        parse_duration(text)


@pytest.mark.parametrize('text, minutes', [('+12:30', 750), (' -1:45 ', -105), ('-0:00', 0), ('-1.5', -90), ('+2h', 120)])
def test_parse_signed_duration(text, minutes):
    assert parse_signed_duration(text) == minutes


@pytest.mark.parametrize('text', ['', '-', '+-1:00', '--1:00', '1:5'])
def test_parse_signed_duration_rejects_invalid(text):
    with pytest.raises(TimeFormatError):
        parse_signed_duration(text)


def test_format_duration():
    assert [format_duration(minutes) for minutes in (0, 90, 1500, -15)] == ['0:00', '1:30', '25:00', '-0:15']


@pytest.mark.parametrize('text, minutes', [('8', 480), ('1,5', 90), ('1.25', 75), (' 4,0 ', 240)])
def test_parse_decimal_hours(text, minutes):
    assert parse_decimal_hours(text) == minutes


@pytest.mark.parametrize('text', ['', ',5', '1,', '1,5h', '-1', '1:30', '0,333'])
def test_parse_decimal_hours_rejects_invalid(text):
    with pytest.raises(TimeFormatError):
        parse_decimal_hours(text)


def test_is_quarter_hour():
    assert [is_quarter_hour(minutes) for minutes in (0, 90, -15, 20)] == [True, True, True, False]


@pytest.mark.parametrize('total, parts, shares', [
    (180, 2, [90, 90]),
    (60, 3, [30, 15, 15]),  # quarter hours, the first ones get more
    (30, 4, [15, 15, 0, 0]),
    (50, 2, [35, 15]),  # a total that is no quarter hour: the rest goes to the first
])
def test_split_evenly(total, parts, shares):
    assert split_evenly(total, parts) == shares


@pytest.mark.parametrize('total, parts', [(60, 0), (-15, 2)])
def test_split_evenly_rejects_invalid(total, parts):
    with pytest.raises(ValueError):
        split_evenly(total, parts)


@pytest.mark.parametrize('text', ['1.5', '8', '1h30m'])
def test_hours_minutes_stay_strict(text):
    with pytest.raises(TimeFormatError):
        parse_hours_minutes(text)
