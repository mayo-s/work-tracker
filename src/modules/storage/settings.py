"""Reading and saving user settings."""

import sqlite3
from typing import Literal, get_args

from src.models.settings import Settings

Theme = Literal['system', 'light', 'dark']


def load_settings(conn: sqlite3.Connection) -> Settings:
    values = dict(conn.execute('SELECT key, value FROM settings'))
    return Settings(balance_start=values['balance_start'], opening_balance=int(values['opening_balance']))


def setup_done(conn: sqlite3.Connection) -> bool:
    """False for a new database until the initial setup (/setup) is finished."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'setup_done'").fetchone()
    return row is None or row[0] == '1'


def finish_setup(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO settings (key, value) VALUES ('setup_done', '1') ON CONFLICT (key) DO UPDATE SET value = '1'")


def load_theme(conn: sqlite3.Connection) -> Theme:
    """The chosen color theme; `system` follows the system setting."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'theme'").fetchone()
    return row[0] if row and row[0] in get_args(Theme) else 'system'


def save_theme(conn: sqlite3.Connection, theme: Theme) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('theme', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (theme,),
    )


def save_settings(conn: sqlite3.Connection, settings: Settings) -> None:
    conn.executemany(
        'INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value',
        [('balance_start', settings.balance_start.isoformat()), ('opening_balance', str(settings.opening_balance))],
    )
