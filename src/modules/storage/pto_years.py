"""PTO years: the allowance, extra days and an optional fixed carry-over per year."""

import sqlite3
from decimal import Decimal

from src.lib.balances import PtoTerms
from src.models.pto import PtoYear
from src.modules.storage.errors import NotFoundError

_COLUMNS = 'year, allowance, extra_days, carried_over, note'


class PtoYearRepository:
    """The PTO years of one user; works within the transaction of the given connection."""

    def __init__(self, conn: sqlite3.Connection, user_id: str) -> None:
        self._conn = conn
        self._user = user_id

    def all(self) -> list[PtoYear]:
        rows = self._conn.execute(f'SELECT {_COLUMNS} FROM pto_years WHERE user_id = ? ORDER BY year', (self._user,))
        return [PtoYear(**dict(row)) for row in rows]

    def get(self, year: int) -> PtoYear:
        sql = f'SELECT {_COLUMNS} FROM pto_years WHERE user_id = ? AND year = ?'
        row = self._conn.execute(sql, (self._user, year)).fetchone()
        if row is None:
            raise NotFoundError(f'No PTO days entered for {year}')
        return PtoYear(**dict(row))

    def save(self, pto_year: PtoYear) -> PtoYear:
        """Insert or replace the year."""
        self._conn.execute(
            f'INSERT OR REPLACE INTO pto_years (user_id, {_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)',
            (self._user, pto_year.year, str(pto_year.allowance), str(pto_year.extra_days), _text(pto_year.carried_over),
             pto_year.note),
        )
        return pto_year

    def delete(self, year: int) -> None:
        if not self._conn.execute('DELETE FROM pto_years WHERE user_id = ? AND year = ?', (self._user, year)).rowcount:
            raise NotFoundError(f'No PTO days entered for {year}')

    def replace_all(self, pto_years: list[PtoYear]) -> None:
        """The given years as the only ones, e.g. on the initial setup."""
        self._conn.execute('DELETE FROM pto_years WHERE user_id = ?', (self._user,))
        for pto_year in pto_years:
            self.save(pto_year)

    def terms(self) -> dict[int, PtoTerms]:
        return {pto_year.year: pto_year.terms() for pto_year in self.all()}


def _text(days: Decimal | None) -> str | None:
    return None if days is None else str(days)
