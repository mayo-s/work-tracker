"""PTO years: the allowance, extra days and an optional fixed carry-over per year."""

import sqlite3
from decimal import Decimal

from src.lib.balances import PtoTerms
from src.models.pto import PtoYear
from src.modules.storage.errors import NotFoundError

_COLUMNS = 'year, allowance, extra_days, carried_over, note'


class PtoYearRepository:
    """Works within the transaction of the given connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def all(self) -> list[PtoYear]:
        return [PtoYear(**dict(row)) for row in self._conn.execute(f'SELECT {_COLUMNS} FROM pto_years ORDER BY year')]

    def get(self, year: int) -> PtoYear:
        row = self._conn.execute(f'SELECT {_COLUMNS} FROM pto_years WHERE year = ?', (year,)).fetchone()
        if row is None:
            raise NotFoundError(f'No PTO days entered for {year}')
        return PtoYear(**dict(row))

    def save(self, pto_year: PtoYear) -> PtoYear:
        """Insert or replace the year."""
        self._conn.execute(
            f'INSERT OR REPLACE INTO pto_years ({_COLUMNS}) VALUES (?, ?, ?, ?, ?)',
            (pto_year.year, str(pto_year.allowance), str(pto_year.extra_days), _text(pto_year.carried_over), pto_year.note),
        )
        return pto_year

    def delete(self, year: int) -> None:
        if not self._conn.execute('DELETE FROM pto_years WHERE year = ?', (year,)).rowcount:
            raise NotFoundError(f'No PTO days entered for {year}')

    def terms(self) -> dict[int, PtoTerms]:
        return {pto_year.year: pto_year.terms() for pto_year in self.all()}


def _text(days: Decimal | None) -> str | None:
    return None if days is None else str(days)
