"""SQLite only: the settings a new database seeds; the shared behaviour is in test_contract_users.py."""

import datetime as dt

from src.models.settings import Settings
from src.modules.storage.settings import load_settings, load_theme
from src.tests.users import USER


def test_seeded_settings(database):
    with database.transaction() as conn:
        settings = load_settings(conn, USER)
    assert settings == Settings(balance_start=dt.date(2024, 6, 1), opening_balance=0)


def test_unknown_stored_theme_follows_the_system(conn):
    conn.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?, 'theme', 'blue')", (USER,))
    assert load_theme(conn, USER) == 'system'
