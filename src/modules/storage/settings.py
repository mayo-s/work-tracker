"""Reading and saving the settings of a user (balance, setup, theme); `settings` holds app-wide ones."""

import datetime as dt
import sqlite3
from typing import Literal, get_args

from src.models.settings import Settings

Theme = Literal['system', 'light', 'dark']


def _values(conn: sqlite3.Connection, user_id: int) -> dict[str, str]:
    return dict(conn.execute('SELECT key, value FROM user_settings WHERE user_id = ?', (user_id,)).fetchall())


def _save(conn: sqlite3.Connection, user_id: int, values: dict[str, str]) -> None:
    conn.executemany(
        'INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?) '
        'ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value',
        [(user_id, key, value) for key, value in values.items()],
    )


def load_settings(conn: sqlite3.Connection, user_id: int) -> Settings:
    """The user's balance start and opening balance; before the setup: today and 0:00."""
    values = _values(conn, user_id)
    return Settings(balance_start=values.get('balance_start', dt.date.today().isoformat()),
                    opening_balance=int(values.get('opening_balance', '0')))


def save_settings(conn: sqlite3.Connection, user_id: int, settings: Settings) -> None:
    _save(conn, user_id, {
        'balance_start': settings.balance_start.isoformat(), 'opening_balance': str(settings.opening_balance),
    })


def setup_done(conn: sqlite3.Connection, user_id: int) -> bool:
    """False until the user finished the setup (/setup)."""
    return _values(conn, user_id).get('setup_done') == '1'


def finish_setup(conn: sqlite3.Connection, user_id: int) -> None:
    _save(conn, user_id, {'setup_done': '1'})


def load_theme(conn: sqlite3.Connection, user_id: int) -> Theme:
    """The chosen color theme; `system` follows the system setting."""
    theme = _values(conn, user_id).get('theme', 'system')
    return theme if theme in get_args(Theme) else 'system'


def save_theme(conn: sqlite3.Connection, user_id: int, theme: Theme) -> None:
    _save(conn, user_id, {'theme': theme})
