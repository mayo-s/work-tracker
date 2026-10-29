import datetime as dt

from src.models.settings import Settings
from src.modules.storage.settings import finish_setup, load_settings, load_theme, save_settings, save_theme, setup_done


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


def test_setup_done(database, fresh_database):
    with database.transaction() as conn:
        assert setup_done(conn)
    with fresh_database.transaction() as conn:
        assert not setup_done(conn)
        finish_setup(conn)
        assert setup_done(conn)


def test_theme(conn):
    assert load_theme(conn) == 'system'
    save_theme(conn, 'dark')
    assert load_theme(conn) == 'dark'


def test_unknown_stored_theme_follows_the_system(conn):
    conn.execute("INSERT INTO settings (key, value) VALUES ('theme', 'blue')")
    assert load_theme(conn) == 'system'
