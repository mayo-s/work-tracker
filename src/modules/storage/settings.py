"""Reading and saving user settings."""

import sqlite3
from decimal import Decimal

from src.models.settings import Settings


def load_settings(conn: sqlite3.Connection) -> Settings:
    values = dict(conn.execute('SELECT key, value FROM settings'))
    allowances = {year: Decimal(days) for year, days in conn.execute('SELECT year, days FROM pto_allowances')}
    return Settings(
        balance_start=values['balance_start'],
        opening_balance=int(values['opening_balance']),
        pto_allowances=allowances,
    )


def save_settings(conn: sqlite3.Connection, settings: Settings) -> None:
    conn.executemany(
        'INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value',
        [('balance_start', settings.balance_start.isoformat()), ('opening_balance', str(settings.opening_balance))],
    )
    conn.execute('DELETE FROM pto_allowances')
    conn.executemany(
        'INSERT INTO pto_allowances (year, days) VALUES (?, ?)',
        [(year, str(days)) for year, days in sorted(settings.pto_allowances.items())],
    )
