import datetime as dt

import pytest
from pydantic import ValidationError

from src.models.schedules import Schedule


def test_work_days_are_sorted_and_distinct():
    schedule = Schedule(valid_from=dt.date(2027, 3, 1), weekly_minutes=1920, work_days=[4, 1, 2, 3, 1])
    assert schedule.work_days == [1, 2, 3, 4]
    assert schedule.to_work_schedule().daily_target == 480


@pytest.mark.parametrize('values', [
    {'weekly_minutes': -60, 'work_days': [1]},
    {'weekly_minutes': 2400, 'work_days': []},
    {'weekly_minutes': 2400, 'work_days': [0, 1]},
    {'weekly_minutes': 2400, 'work_days': [8]},
])
def test_schedule_rejects_invalid_values(values):
    with pytest.raises(ValidationError):
        Schedule(valid_from=dt.date(2027, 3, 1), **values)
