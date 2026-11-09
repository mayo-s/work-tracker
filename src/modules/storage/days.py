"""Days."""

import datetime as dt
import sqlite3

from src.lib.balances import DayRecord
from src.models.days import Day
from src.modules.storage.errors import NotFoundError

_DAY_COLUMNS = 'date, day_type, start_time, end_time, break_minutes, note'


def _to_day(row: sqlite3.Row) -> Day:
    return Day(
        date=row['date'],
        day_type=row['day_type'],
        start=row['start_time'],
        end=row['end_time'],
        break_minutes=row['break_minutes'],
        note=row['note'],
    )


class DayRepository:
    """Recorded days of one user; works within the transaction of the given connection."""

    def __init__(self, conn: sqlite3.Connection, user_id: str) -> None:
        self._conn = conn
        self._user = user_id

    def get(self, date: dt.date) -> Day | None:
        row = self._conn.execute(f'SELECT {_DAY_COLUMNS} FROM days WHERE user_id = ? AND date = ?',
                                 (self._user, date.isoformat())).fetchone()
        return _to_day(row) if row else None

    def between(self, start: dt.date, end: dt.date) -> list[Day]:
        """Recorded days from start to end (inclusive), in date order."""
        rows = self._conn.execute(
            f'SELECT {_DAY_COLUMNS} FROM days WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date',
            (self._user, start.isoformat(), end.isoformat()),
        )
        return [_to_day(row) for row in rows]

    def records(self, start: dt.date, end: dt.date) -> dict[dt.date, DayRecord]:
        """Worked time and day type of the recorded days, as input for balances."""
        return {day.date: day.to_record() for day in self.between(start, end)}

    def save(self, day: Day) -> None:
        """Insert or replace the day."""
        self._conn.execute(
            f'INSERT INTO days (user_id, {_DAY_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?) '
            'ON CONFLICT (user_id, date) DO UPDATE SET day_type = excluded.day_type, start_time = excluded.start_time, '
            'end_time = excluded.end_time, break_minutes = excluded.break_minutes, note = excluded.note',
            (self._user, day.date.isoformat(), day.day_type, day.start, day.end, day.break_minutes, day.note),
        )

    def delete(self, date: dt.date) -> None:
        """Delete the day."""
        if not self._conn.execute('DELETE FROM days WHERE user_id = ? AND date = ?', (self._user, date.isoformat())).rowcount:
            raise NotFoundError(f'No day recorded on {date}')
