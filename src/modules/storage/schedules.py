"""Work schedules, each valid from a date; at least one always exists."""

import sqlite3

from src.lib.schedules import Schedules
from src.models.schedules import Schedule
from src.modules.storage.errors import ConflictError, NotFoundError

_COLUMNS = 'id, valid_from, weekly_minutes, work_days'


class ScheduleRepository:
    """Works within the transaction of the given connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def all(self) -> list[Schedule]:
        rows = self._conn.execute(f'SELECT {_COLUMNS} FROM work_schedules ORDER BY valid_from')
        return [_schedule(row) for row in rows]

    def get(self, schedule_id: int) -> Schedule:
        row = self._conn.execute(f'SELECT {_COLUMNS} FROM work_schedules WHERE id = ?', (schedule_id,)).fetchone()
        if row is None:
            raise NotFoundError(f'No work schedule with id {schedule_id}')
        return _schedule(row)

    def add(self, schedule: Schedule) -> Schedule:
        sql = 'INSERT INTO work_schedules (valid_from, weekly_minutes, work_days) VALUES (?, ?, ?)'
        cursor = self._write(sql, _values(schedule), schedule)
        return schedule.model_copy(update={'id': cursor.lastrowid})

    def update(self, schedule: Schedule) -> Schedule:
        sql = 'UPDATE work_schedules SET valid_from = ?, weekly_minutes = ?, work_days = ? WHERE id = ?'
        if not self._write(sql, (*_values(schedule), schedule.id), schedule).rowcount:
            raise NotFoundError(f'No work schedule with id {schedule.id}')
        return schedule

    def delete(self, schedule_id: int) -> None:
        self.get(schedule_id)
        if len(self.all()) == 1:
            raise ConflictError('The only work schedule cannot be deleted')
        self._conn.execute('DELETE FROM work_schedules WHERE id = ?', (schedule_id,))

    def schedules(self) -> Schedules:
        """All schedules for the calculations: each day follows the latest one starting on or before it."""
        return Schedules(schedule.to_work_schedule() for schedule in self.all())

    def _write(self, sql: str, params: tuple, schedule: Schedule) -> sqlite3.Cursor:
        try:
            return self._conn.execute(sql, params)
        except sqlite3.IntegrityError as error:
            raise ConflictError(f'A work schedule from {schedule.valid_from:%d.%m.%Y} already exists') from error


def _values(schedule: Schedule) -> tuple:
    return schedule.valid_from.isoformat(), schedule.weekly_minutes, ','.join(map(str, schedule.work_days))


def _schedule(row: sqlite3.Row) -> Schedule:
    return Schedule(
        id=row['id'], valid_from=row['valid_from'], weekly_minutes=row['weekly_minutes'],
        work_days=[int(day) for day in row['work_days'].split(',')],
    )
