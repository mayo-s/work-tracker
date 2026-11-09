"""Days on DynamoDB (`DAY#<date>` in the user's partition), as the SQLite repository (days.py)."""

import datetime as dt

from src.lib.balances import DayRecord
from src.models.days import Day
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
        """Delete the day."""
        if self.get(date) is None:
            raise NotFoundError(f'No day recorded on {date}')
        self._unit.delete(self._pk, day_key(date))
