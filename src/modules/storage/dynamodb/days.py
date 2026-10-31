"""Days and their review flags on DynamoDB (`DAY#<date>` in the user's partition), as the SQLite repository (days.py)."""

import datetime as dt

from src.lib.balances import DayRecord
from src.models.days import Day
from src.models.review import FlagReason, ReviewFlag
from src.modules.storage.dynamodb.flags import add_flag, all_flags, delete_flags, flag_key
from src.modules.storage.dynamodb.keys import user_partition
from src.modules.storage.dynamodb.table import attributes
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.errors import NotFoundError

DAY = 'DAY#'


def day_key(date: dt.date) -> str:
    return DAY + date.isoformat()


class DynamoDays:
    """Recorded days of one user."""

    def __init__(self, unit: Unit, user_id: str) -> None:
        self._unit = unit
        self._pk = user_partition(user_id)

    def get(self, date: dt.date) -> Day | None:
        item = self._unit.get(self._pk, day_key(date))
        return Day(**attributes(item)) if item else None

    def between(self, start: dt.date, end: dt.date) -> list[Day]:
        """Recorded days from start to end (inclusive), in date order."""
        return [Day(**attributes(item)) for item in self._unit.query(self._pk, day_key(start), day_key(end))]

    def records(self, start: dt.date, end: dt.date) -> dict[dt.date, DayRecord]:
        """Worked time and day type of the recorded days, as input for balances."""
        return {day.date: day.to_record() for day in self.between(start, end)}

    def save(self, day: Day) -> None:
        """Insert or replace the day."""
        self._unit.put({'PK': self._pk, 'SK': day_key(day.date), **day.model_dump(mode='json')})

    def delete(self, date: dt.date) -> None:
        """Delete the day and its review flags."""
        if self.get(date) is None:
            raise NotFoundError(f'No day recorded on {date}')
        self._unit.delete(self._pk, day_key(date))
        delete_flags(self._unit, self._pk, lambda flag: flag.date == date)

    def add_flag(self, date: dt.date, reason: FlagReason, detail: str = '') -> ReviewFlag:
        return add_flag(self._unit, self._pk, ReviewFlag(date=date, reason=reason, detail=detail))

    def flags_on(self, date: dt.date) -> list[ReviewFlag]:
        return [flag for flag in all_flags(self._unit, self._pk) if flag.date == date]

    def day_flags(self) -> list[ReviewFlag]:
        """All flags on days, in date order."""
        flags = [flag for flag in all_flags(self._unit, self._pk) if flag.date is not None]
        return sorted(flags, key=lambda flag: (flag.date, flag.id))

    def clear_flag(self, flag_id: str) -> None:
        item = self._unit.get(self._pk, flag_key(flag_id))
        if item is None or item['date'] is None:
            raise NotFoundError(f'No day flag with id {flag_id}')
        self._unit.delete(self._pk, flag_key(flag_id))
