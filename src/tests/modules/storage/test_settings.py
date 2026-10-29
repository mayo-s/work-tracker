import datetime as dt

from src.models.settings import Settings
from src.modules.storage.settings import finish_setup, load_settings, load_theme, save_settings, save_theme, setup_done
from src.tests.users import USER


def test_seeded_settings(database):
    with database.transaction() as conn:
        settings = load_settings(conn, USER)
    assert settings == Settings(balance_start=dt.date(2024, 6, 1), opening_balance=0)


def test_save_and_load_settings(database):
    changed = Settings(balance_start=dt.date(2024, 6, 1), opening_balance=-90)
    with database.transaction() as conn:
        save_settings(conn, USER, changed)
    with database.transaction() as conn:
        assert load_settings(conn, USER) == changed


def test_setup_done(database, fresh_database):
    with database.transaction() as conn:
        assert setup_done(conn, USER)
    with fresh_database.transaction() as conn:
        assert not setup_done(conn, USER)
        finish_setup(conn, USER)
        assert setup_done(conn, USER)


def test_theme(conn):
    assert load_theme(conn, USER) == 'system'
    save_theme(conn, USER, 'dark')
    assert load_theme(conn, USER) == 'dark'


def test_unknown_stored_theme_follows_the_system(conn):
    conn.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?, 'theme', 'blue')", (USER,))
    assert load_theme(conn, USER) == 'system'
