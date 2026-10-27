import datetime as dt

import pytest

from src.lib.dates import each_day


def test_each_day_inclusive_across_month_end():
    assert list(each_day(dt.date(2026, 2, 27), dt.date(2026, 3, 2))) == [
        dt.date(2026, 2, 27),
        dt.date(2026, 2, 28),
        dt.date(2026, 3, 1),
        dt.date(2026, 3, 2),
    ]


def test_each_day_single_day():
    assert list(each_day(dt.date(2026, 10, 27), dt.date(2026, 10, 27))) == [dt.date(2026, 10, 27)]


def test_each_day_rejects_end_before_start():
    days = each_day(dt.date(2026, 10, 27), dt.date(2026, 10, 26))
    with pytest.raises(ValueError):
        next(days)
