"""SQLite only: the schedule the migration creates; the shared behaviour is in test_contract_schedules.py."""

import datetime as dt

import pytest

from src.modules.storage.schedules import ScheduleRepository
from src.tests.users import USER


@pytest.fixture
def schedules(conn):
    return ScheduleRepository(conn, USER)


def test_migrated_schedule_starts_with_the_balance(schedules):
    [schedule] = schedules.all()
    assert (schedule.valid_from, schedule.weekly_minutes, schedule.work_days) == (dt.date(2024, 6, 1), 2400, [1, 2, 3, 4, 5])
    assert (schedule.state, schedule.company_half_days) == ('BE', True)
