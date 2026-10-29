"""Work schedules: hours per week on chosen work days, each valid from a date until the next one starts."""

import bisect
import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

MINUTES_PER_WEEK = 7 * 24 * 60
WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


@dataclass(frozen=True)
class WorkSchedule:
    valid_from: dt.date
    weekly_minutes: int
    work_days: frozenset[int]  # ISO weekdays: Monday = 1 … Sunday = 7

    def __post_init__(self) -> None:
        if not 0 <= self.weekly_minutes <= MINUTES_PER_WEEK:
            raise ValueError(f'{self.weekly_minutes} minutes per week is out of range')
        if not self.work_days or not self.work_days <= set(range(1, 8)):
            raise ValueError('work days must be one or more weekdays (1 = Monday … 7 = Sunday)')

    @property
    def daily_target(self) -> int:
        """The weekly hours split evenly over the work days, in whole minutes (40 h / 5 days = 8:00)."""
        return self.weekly_minutes // len(self.work_days)

    def is_work_day(self, date: dt.date) -> bool:
        return date.isoweekday() in self.work_days


STANDARD = WorkSchedule(dt.date.min, 40 * 60, frozenset(range(1, 6)))


class Schedules:
    """The schedule of each day: the latest one starting on or before it; days before the first one follow the first."""

    def __init__(self, schedules: Iterable[WorkSchedule] = (STANDARD,)) -> None:
        self._schedules = sorted(schedules, key=lambda schedule: schedule.valid_from)
        if not self._schedules:
            raise ValueError('At least one work schedule is needed')
        self._starts = [schedule.valid_from for schedule in self._schedules]

    def on(self, date: dt.date) -> WorkSchedule:
        return self._schedules[max(bisect.bisect_right(self._starts, date) - 1, 0)]


STANDARD_SCHEDULES = Schedules()
