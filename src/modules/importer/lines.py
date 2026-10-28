"""Helpers for the lines of a spreadsheet comment."""

import re

from src.lib.durations import MINUTES_PER_DAY, parse_decimal_hours

_HOURS = re.compile(r'(\d+(?:,\d+)?)(?:\s+(.*))?')


def split_hours(line: str) -> tuple[int | None, str]:
    """Leading decimal-comma hours and the rest of the line: '1,5 KP-2035 refinement' → (90, 'KP-2035 refinement').

    Lines without leading hours (or with more than 24 hours, i.e. not hours at all) return (None, line).
    """
    match = _HOURS.fullmatch(line.strip())
    if not match:
        return None, line.strip()
    minutes = parse_decimal_hours(match[1])
    if minutes > MINUTES_PER_DAY:
        return None, line.strip()
    return minutes, match[2] or ''
