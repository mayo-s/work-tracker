import pytest

from src.lib.durations import (
    TimeFormatError,
    format_clock,
    format_duration,
    is_quarter_hour,
    parse_clock,
    parse_duration,
    parse_signed_duration,
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


def test_is_quarter_hour():
    assert [is_quarter_hour(minutes) for minutes in (0, 90, -15, 20)] == [True, True, True, False]
