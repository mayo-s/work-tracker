from decimal import Decimal

import pytest

from src.lib.balances import PtoTerms
from src.models.pto import PtoYear
from src.modules.storage import migrations
from src.modules.storage.database import Database
from src.modules.storage.errors import NotFoundError
from src.modules.storage.owners import NO_OWNER
from src.modules.storage.pto_years import PtoYearRepository
from src.tests.users import USER


def test_replace_all(conn):
    years = PtoYearRepository(conn, USER)
    years.replace_all([PtoYear(year=2027, allowance=Decimal(25)), PtoYear(year=2028, allowance=Decimal(30))])
    assert [(year.year, year.allowance) for year in years.all()] == [(2027, 25), (2028, 30)]


def test_migration_takes_over_the_allowances(tmp_path, monkeypatch):
    db = Database(tmp_path / 'old.db')
    monkeypatch.setattr(migrations, 'MIGRATIONS', migrations.MIGRATIONS[:2])
    db.migrate()
    with db.transaction() as conn:
        conn.execute("INSERT INTO pto_allowances (year, days) VALUES (2028, '28')")
        conn.execute("INSERT INTO days (date, day_type) VALUES ('2026-10-28', 'pto')")  # in use: migration 6 keeps it
    monkeypatch.undo()
    db.migrate()
    with db.transaction() as conn:  # no user yet: no owner
        assert PtoYearRepository(conn, NO_OWNER).get(2028) == PtoYear(year=2028, allowance=Decimal(28))


def test_save_inserts_and_replaces(conn):
    years = PtoYearRepository(conn, USER)
    changed = PtoYear(year=2026, allowance=Decimal(30), extra_days=Decimal(1), carried_over=Decimal(3), note='extra day')
    years.save(PtoYear(year=2030, allowance=Decimal(30)))
    years.save(changed)
    assert years.get(2026) == changed
    assert years.get(2030).carried_over is None


def test_get_missing_year(conn):
    years = PtoYearRepository(conn, USER)
    with pytest.raises(NotFoundError):
        years.get(2023)


def test_delete(conn):
    years = PtoYearRepository(conn, USER)
    years.delete(2027)
    assert 2027 not in years.terms()


def test_delete_missing_year(conn):
    years = PtoYearRepository(conn, USER)
    with pytest.raises(NotFoundError):
        years.delete(2023)


def test_terms(conn):
    years = PtoYearRepository(conn, USER)
    years.save(PtoYear(year=2026, allowance=Decimal(30), extra_days=Decimal(1), carried_over=Decimal(3)))
    assert years.terms()[2026] == PtoTerms(Decimal(30), Decimal(1), Decimal(3))
