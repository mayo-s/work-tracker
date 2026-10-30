"""Work schedules (`SCHEDULE#<id>`, at most one per day by `SCHEDULE_FROM#<date>`) and PTO years (`PTO#<year>`) in the
user's partition, as the SQLite repositories (schedules.py, pto_years.py)."""

from src.lib.balances import PtoTerms
from src.lib.schedules import STANDARD, Schedules
from src.models.pto import PtoYear
from src.models.schedules import Schedule
from src.modules.storage.dynamodb.keys import user_partition
from src.modules.storage.dynamodb.table import attributes
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.errors import ConflictError, NotFoundError

SCHEDULE, PTO = 'SCHEDULE#', 'PTO#'


class DynamoSchedules:
    """The work schedules of one user, each valid from a day on."""

    def __init__(self, unit: Unit, user_id: str) -> None:
        self._unit = unit
        self._pk = user_partition(user_id)

    def all(self) -> list[Schedule]:
        schedules = [Schedule(**attributes(item)) for item in self._unit.query_prefix(self._pk, SCHEDULE)]
        return sorted(schedules, key=lambda schedule: schedule.valid_from)

    def get(self, schedule_id: int) -> Schedule:
        item = self._unit.get(self._pk, _key(schedule_id))
        if item is None:
            raise NotFoundError(f'No work schedule with id {schedule_id}')
        return Schedule(**attributes(item))

    def add(self, schedule: Schedule) -> Schedule:
        added = schedule.model_copy(update={'id': self._unit.next_id('schedule')})
        self._claim(added)
        self._save(added)
        return added

    def update(self, schedule: Schedule) -> Schedule:
        stored = self.get(schedule.id)
        if stored.valid_from != schedule.valid_from:
            self._claim(schedule)
            self._unit.delete(self._pk, _from_key(stored))
        self._save(schedule)
        return schedule

    def delete(self, schedule_id: int) -> None:
        stored = self.get(schedule_id)
        if len(self.all()) == 1:
            raise ConflictError('The only work schedule cannot be deleted')
        self._unit.delete(self._pk, _key(schedule_id))
        self._unit.delete(self._pk, _from_key(stored))

    def replace_all(self, schedule: Schedule) -> Schedule:
        """The given schedule as the only one, e.g. on the initial setup."""
        for stored in self.all():
            self._unit.delete(self._pk, _key(stored.id))
            self._unit.delete(self._pk, _from_key(stored))
        return self.add(schedule)

    def schedules(self) -> Schedules:
        """All schedules for the calculations: each day follows the latest one starting on or before it (without any
        yet, e.g. before the setup: 40 h, Monday to Friday, Berlin)."""
        return Schedules([schedule.to_work_schedule() for schedule in self.all()] or [STANDARD])

    def _claim(self, schedule: Schedule) -> None:
        self._unit.put({'PK': self._pk, 'SK': _from_key(schedule), 'id': schedule.id},
                       unique=f'A work schedule from {schedule.valid_from:%d.%m.%Y} already exists')

    def _save(self, schedule: Schedule) -> None:
        self._unit.put({'PK': self._pk, 'SK': _key(schedule.id), **schedule.model_dump(mode='json')})


def _key(schedule_id: int) -> str:
    return f'{SCHEDULE}{schedule_id:010d}'


def _from_key(schedule: Schedule) -> str:
    return f'SCHEDULE_FROM#{schedule.valid_from.isoformat()}'


class DynamoPtoYears:
    """The PTO years of one user."""

    def __init__(self, unit: Unit, user_id: str) -> None:
        self._unit = unit
        self._pk = user_partition(user_id)

    def all(self) -> list[PtoYear]:
        return [PtoYear(**attributes(item)) for item in self._unit.query_prefix(self._pk, PTO)]

    def get(self, year: int) -> PtoYear:
        item = self._unit.get(self._pk, f'{PTO}{year}')
        if item is None:
            raise NotFoundError(f'No PTO days entered for {year}')
        return PtoYear(**attributes(item))

    def save(self, pto_year: PtoYear) -> PtoYear:
        """Insert or replace the year."""
        self._unit.put({'PK': self._pk, 'SK': f'{PTO}{pto_year.year}', 'year': pto_year.year, 'allowance': pto_year.allowance,
                        'extra_days': pto_year.extra_days, 'carried_over': pto_year.carried_over, 'note': pto_year.note})
        return pto_year

    def delete(self, year: int) -> None:
        self.get(year)
        self._unit.delete(self._pk, f'{PTO}{year}')

    def replace_all(self, pto_years: list[PtoYear]) -> None:
        """The given years as the only ones, e.g. on the initial setup."""
        for stored in self.all():
            self._unit.delete(self._pk, f'{PTO}{stored.year}')
        for pto_year in pto_years:
            self.save(pto_year)

    def terms(self) -> dict[int, PtoTerms]:
        return {pto_year.year: pto_year.terms() for pto_year in self.all()}
