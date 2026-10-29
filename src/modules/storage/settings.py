"""Reading and saving user settings."""

import sqlite3

from src.models.settings import Settings


def load_settings(conn: sqlite3.Connection) -> Settings:
    values = dict(conn.execute('SELECT key, value FROM settings'))
    return Settings(balance_start=values['balance_start'], opening_balance=int(values['opening_balance']))


def save_settings(conn: sqlite3.Connection, settings: Settings) -> None:
    conn.executemany(
        'INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value',
        [('balance_start', settings.balance_start.isoformat()), ('opening_balance', str(settings.opening_balance))],
    )
