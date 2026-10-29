import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.models.settings import Settings
from src.modules.storage.settings import load_settings, save_settings


def test_seeded_settings(database):
    with database.transaction() as conn:
        settings = load_settings(conn)
    assert settings == Settings(
        balance_start=dt.date(2024, 6, 1),
        opening_balance=0,
        pto_allowances={2024: Decimal('17.5'), 2025: Decimal(31), 2026: Decimal(31), 2027: Decimal(30)},
    )


def test_save_and_load_settings(database):
    changed = Settings(
        balance_start=dt.date(2024, 6, 1),
        opening_balance=-90,
        pto_allowances={2024: Decimal('17.5'), 2025: Decimal(30), 2027: Decimal(28)},
    )
    with database.transaction() as conn:
        save_settings(conn, changed)
    with database.transaction() as conn:
        assert load_settings(conn) == changed


@pytest.mark.parametrize('allowance', ['-1', '17.25'])
def test_settings_reject_invalid_allowance(allowance):
    with pytest.raises(ValidationError):
        Settings(balance_start=dt.date(2024, 6, 1), pto_allowances={2024: Decimal(allowance)})
