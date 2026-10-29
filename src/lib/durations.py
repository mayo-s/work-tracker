"""Parsing and formatting of clock times and durations, all handled as whole minutes."""

import re
from decimal import Decimal

MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR
QUARTER_HOUR = 15

_CLOCK = re.compile(r'(\d{1,2}):(\d{2})')
_DURATION = re.compile(r'(\d+):(\d{2})')
_DECIMAL_HOURS = re.compile(r'\d+(?:[,.]\d+)?')


class TimeFormatError(ValueError):
    """Raised when a clock time or duration string cannot be parsed."""


def parse_clock(text: str) -> int:
    """Parse a 24 h clock time (`08:15`, `7:15`) into minutes since midnight."""
    match = _CLOCK.fullmatch(text.strip())
    if not match:
        raise TimeFormatError(f'Invalid time {text!r}, expected HH:MM')
    hours, minutes = int(match[1]), int(match[2])
    if hours > 23 or minutes >= MINUTES_PER_HOUR:
        raise TimeFormatError(f'Invalid time {text!r}, out of range')
    return hours * MINUTES_PER_HOUR + minutes


def format_clock(minutes: int) -> str:
    """Format minutes since midnight as `HH:MM`."""
    if not 0 <= minutes < MINUTES_PER_DAY:
        raise ValueError(f'{minutes} minutes is not a time of day')
    hours, rest = divmod(minutes, MINUTES_PER_HOUR)
    return f'{hours:02d}:{rest:02d}'


def parse_duration(text: str) -> int:
    """Parse a duration in `h:mm` format (`1:30`, `0:45`, `12:00`) into minutes."""
    match = _DURATION.fullmatch(text.strip())
    if not match:
        raise TimeFormatError(f'Invalid duration {text!r}, expected h:mm')
    hours, minutes = int(match[1]), int(match[2])
    if minutes >= MINUTES_PER_HOUR:
        raise TimeFormatError(f'Invalid duration {text!r}, minutes out of range')
    return hours * MINUTES_PER_HOUR + minutes


def parse_signed_duration(text: str) -> int:
    """Parse a duration that may be negative (`-1:45`, `+12:30`, `0:15`), e.g. an overtime balance."""
    cleaned = text.strip()
    if cleaned[:1] in ('-', '+'):
        minutes = parse_duration(cleaned[1:])
        return -minutes if cleaned[0] == '-' else minutes
    return parse_duration(cleaned)


def format_duration(minutes: int) -> str:
    """Format minutes as `h:mm`; negative values (overtime) get a leading minus."""
    sign = '-' if minutes < 0 else ''
    hours, rest = divmod(abs(minutes), MINUTES_PER_HOUR)
    return f'{sign}{hours}:{rest:02d}'


def parse_decimal_hours(text: str) -> int:
    """Parse spreadsheet hours with a decimal comma (`1,5`, `0,75`, `8`) into minutes."""
    cleaned = text.strip()
    if not _DECIMAL_HOURS.fullmatch(cleaned):
        raise TimeFormatError(f'Invalid hours {text!r}, expected e.g. 1,5')
    minutes = Decimal(cleaned.replace(',', '.')) * MINUTES_PER_HOUR
    if minutes != minutes.to_integral_value():
        raise TimeFormatError(f'Hours {text!r} are not a whole number of minutes')
    return int(minutes)


def is_quarter_hour(minutes: int) -> bool:
    return minutes % QUARTER_HOUR == 0


def split_evenly(total: int, parts: int) -> list[int]:
    """Split minutes into quarter-hour shares; leftovers go to the first shares (90 / 4 → 30, 30, 15, 15)."""
    if parts < 1:
        raise ValueError('parts must be at least 1')
    if total < 0:
        raise ValueError('total must not be negative')
    quarters, leftover = divmod(total, QUARTER_HOUR)
    base, extra = divmod(quarters, parts)
    shares = [(base + 1 if index < extra else base) * QUARTER_HOUR for index in range(parts)]
    shares[0] += leftover
    return shares
