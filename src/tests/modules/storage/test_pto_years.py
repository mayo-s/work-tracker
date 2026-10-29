from decimal import Decimal

import pytest

from src.lib.balances import PtoTerms
from src.models.pto import PtoYear
from src.modules.storage import migrations
from src.modules.storage.database import Database
from src.modules.storage.errors import NotFoundError
from src.modules.storage.pto_years import PtoYearRepository


def test_migrated_years(conn):
    years = PtoYearRepository(conn).all()
    assert [(year.year, year.allowance, year.extra_days, year.carried_over) for year in years] == [
        (2024, Decimal('17.5'), 0, None), (2025, 31, 0, None), (2026, 31, 0, None), (2027, 30, 0, None),
    ]


def test_migration_takes_over_the_allowances(tmp_path, monkeypatch):
    db = Database(tmp_path / 'old.db')
    monkeypatch.setattr(migrations, 'MIGRATIONS', migrations.MIGRATIONS[:2])
    db.migrate()
    with db.transaction() as conn:
        conn.execute("INSERT INTO pto_allowances (year, days) VALUES (2028, '28')")
    monkeypatch.undo()
    db.migrate()
    with db.transaction() as conn:
        assert PtoYearRepository(conn).get(2028) == PtoYear(year=2028, allowance=Decimal(28))


def test_save_inserts_and_replaces(conn):
    years = PtoYearRepository(conn)
    changed = PtoYear(year=2026, allowance=Decimal(30), extra_days=Decimal(1), carried_over=Decimal(3), note='extra day')
    years.save(PtoYear(year=2030, allowance=Decimal(30)))
    years.save(changed)
    assert years.get(2026) == changed
    assert years.get(2030).carried_over is None


def test_get_missing_year(conn):
    years = PtoYearRepository(conn)
    with pytest.raises(NotFoundError):
        years.get(2023)


def test_terms(conn):
    years = PtoYearRepository(conn)
    years.save(PtoYear(year=2026, allowance=Decimal(30), extra_days=Decimal(1), carried_over=Decimal(3)))
    assert years.terms()[2026] == PtoTerms(Decimal(30), Decimal(1), Decimal(3))
