import datetime as dt

import pytest
from pydantic import ValidationError

from src.models.schedules import Schedule


def test_work_days_are_sorted_and_berlin_is_the_default():
    schedule = Schedule(valid_from=dt.date(2027, 3, 1), weekly_minutes=1920, work_days=[4, 1, 2, 3, 1])
    assert schedule.work_days == [1, 2, 3, 4]
    work_schedule = schedule.to_work_schedule()
    assert (work_schedule.daily_target, work_schedule.holidays.state, work_schedule.holidays.company_half_days) == (
        480, 'BE', True)  # Berlin with company half days by default


@pytest.mark.parametrize('values', [
    {'weekly_minutes': 2400, 'work_days': []},
    {'weekly_minutes': 2400, 'work_days': [1], 'state': 'Bayern'},
])
def test_schedule_rejects_invalid_values(values):
    with pytest.raises(ValidationError):
        Schedule(valid_from=dt.date(2027, 3, 1), **values)
