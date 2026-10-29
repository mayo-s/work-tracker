import datetime as dt

import pytest

from src.lib.schedules import STANDARD, Schedules, WorkSchedule

MONDAY_TO_FRIDAY = frozenset(range(1, 6))


@pytest.mark.parametrize('hours, days, target', [
    (40, MONDAY_TO_FRIDAY, 480), (32, frozenset(range(1, 5)), 480), (30, MONDAY_TO_FRIDAY, 360),
    (39, MONDAY_TO_FRIDAY, 468), (40, frozenset(range(1, 8)), 342),
])
def test_daily_target_splits_the_week_evenly_in_whole_minutes(hours, days, target):
    assert WorkSchedule(dt.date(2027, 1, 1), hours * 60, days).daily_target == target


def test_standard_schedule_is_40_hours_monday_to_friday():
    friday, saturday = dt.date(2026, 10, 30), dt.date(2026, 10, 31)
    assert (STANDARD.daily_target, STANDARD.is_work_day(friday), STANDARD.is_work_day(saturday)) == (480, True, False)


@pytest.mark.parametrize('minutes, days', [(-1, MONDAY_TO_FRIDAY), (10081, MONDAY_TO_FRIDAY), (2400, frozenset()),
                                           (2400, frozenset({0, 1}))])
def test_schedule_rejects_invalid_values(minutes, days):
    with pytest.raises(ValueError):
        WorkSchedule(dt.date(2027, 1, 1), minutes, days)


def test_each_day_follows_the_latest_schedule_started():
    four_days = WorkSchedule(dt.date(2027, 3, 1), 32 * 60, frozenset(range(1, 5)))
    full_time = WorkSchedule(dt.date(2026, 1, 1), 40 * 60, MONDAY_TO_FRIDAY)
    schedules = Schedules([four_days, full_time])
    assert schedules.on(dt.date(2027, 2, 28)) is full_time
    assert schedules.on(dt.date(2027, 3, 1)) is four_days
    assert schedules.on(dt.date(2025, 6, 1)) is full_time  # before the first one: the first one


def test_schedules_need_at_least_one():
    with pytest.raises(ValueError):
        Schedules([])
