import datetime as dt

from src.models.settings import Settings
from src.modules.storage.settings import load_settings, save_settings


def test_seeded_settings(database):
    with database.transaction() as conn:
        settings = load_settings(conn)
    assert settings == Settings(balance_start=dt.date(2024, 6, 1), opening_balance=0)


def test_save_and_load_settings(database):
    changed = Settings(balance_start=dt.date(2024, 6, 1), opening_balance=-90)
    with database.transaction() as conn:
        save_settings(conn, changed)
    with database.transaction() as conn:
        assert load_settings(conn) == changed
