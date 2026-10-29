import datetime as dt

import pytest

from src.models.schedules import Schedule
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.schedules import ScheduleRepository

PART_TIME = Schedule(valid_from=dt.date(2027, 3, 1), weekly_minutes=1920, work_days=[1, 2, 3, 4])


@pytest.fixture
def schedules(conn):
    return ScheduleRepository(conn)


def test_migrated_schedule_starts_with_the_balance(schedules):
    [schedule] = schedules.all()
    assert (schedule.valid_from, schedule.weekly_minutes, schedule.work_days) == (dt.date(2024, 6, 1), 2400, [1, 2, 3, 4, 5])
    assert (schedule.state, schedule.company_half_days) == ('BE', True)


def test_add_get_and_order(schedules):
    added = schedules.add(PART_TIME)
    assert schedules.get(added.id) == added
    assert [schedule.valid_from for schedule in schedules.all()] == [dt.date(2024, 6, 1), dt.date(2027, 3, 1)]
    assert schedules.schedules().on(dt.date(2027, 3, 5)).daily_target == 480


def test_add_second_schedule_on_the_same_day(schedules):
    duplicate = PART_TIME.model_copy(update={'valid_from': dt.date(2024, 6, 1)})
    with pytest.raises(ConflictError):
        schedules.add(duplicate)


def test_update(schedules):
    added = schedules.add(PART_TIME)
    changed = schedules.update(added.model_copy(update={'weekly_minutes': 1800, 'state': 'HH', 'company_half_days': False}))
    assert schedules.get(added.id) == changed


def test_update_missing_schedule(schedules):
    missing = PART_TIME.model_copy(update={'id': 404})
    with pytest.raises(NotFoundError):
        schedules.update(missing)


def test_delete(schedules):
    added = schedules.add(PART_TIME)
    schedules.delete(added.id)
    assert len(schedules.all()) == 1


def test_only_schedule_cannot_be_deleted(schedules):
    [only] = schedules.all()
    with pytest.raises(ConflictError):
        schedules.delete(only.id)


def test_delete_missing_schedule(schedules):
    with pytest.raises(NotFoundError):
        schedules.delete(404)
