"""Date range helpers."""

import datetime as dt
from collections.abc import Iterator

from src.lib.texts import text


def each_day(start: dt.date, end: dt.date) -> Iterator[dt.date]:
    """Every date from start to end (inclusive)."""
    if end < start:
        raise ValueError(text('End {end} is before start {start}', end=end, start=start))
    for offset in range((end - start).days + 1):
        yield start + dt.timedelta(days=offset)
