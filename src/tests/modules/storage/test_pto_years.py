"""SQLite only: the migration of the former allowances; the shared behaviour is in test_contract_pto_years.py."""

from decimal import Decimal

from src.models.pto import PtoYear
from src.modules.storage import migrations
from src.modules.storage.database import Database
from src.modules.storage.owners import NO_OWNER
from src.modules.storage.pto_years import PtoYearRepository


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
