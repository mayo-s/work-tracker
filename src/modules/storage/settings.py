"""Reading and saving the settings of a user (balance, setup, theme); `settings` holds app-wide ones."""

import datetime as dt
import sqlite3
from typing import Literal, get_args

from src.models.settings import Settings

Theme = Literal['system', 'light', 'dark']


def _values(conn: sqlite3.Connection, user_id: str) -> dict[str, str]:
    return dict(conn.execute('SELECT key, value FROM user_settings WHERE user_id = ?', (user_id,)).fetchall())


def _save(conn: sqlite3.Connection, user_id: str, values: dict[str, str]) -> None:
    conn.executemany(
        'INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?) '
        'ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value',
        [(user_id, key, value) for key, value in values.items()],
    )


def load_settings(conn: sqlite3.Connection, user_id: str) -> Settings:
    """The user's balance start and opening balance; before the setup: today and 0:00."""
    values = _values(conn, user_id)
    return Settings(balance_start=values.get('balance_start', dt.date.today().isoformat()),
                    opening_balance=int(values.get('opening_balance', '0')))


def save_settings(conn: sqlite3.Connection, user_id: str, settings: Settings) -> None:
    _save(conn, user_id, {
        'balance_start': settings.balance_start.isoformat(), 'opening_balance': str(settings.opening_balance),
    })


def setup_done(conn: sqlite3.Connection, user_id: str) -> bool:
    """False until the user finished the setup (/setup)."""
    return _values(conn, user_id).get('setup_done') == '1'


def finish_setup(conn: sqlite3.Connection, user_id: str) -> None:
    _save(conn, user_id, {'setup_done': '1'})


def load_theme(conn: sqlite3.Connection, user_id: str) -> Theme:
    """The chosen color theme; `system` follows the system setting."""
    theme = _values(conn, user_id).get('theme', 'system')
    return theme if theme in get_args(Theme) else 'system'


def save_theme(conn: sqlite3.Connection, user_id: str, theme: Theme) -> None:
    _save(conn, user_id, {'theme': theme})


def registration_open(conn: sqlite3.Connection) -> bool:
    """Whether new users can register on /register (app-wide; off until an admin switches it on)."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'registration'").fetchone()
    return row is not None and row[0] == '1'


def set_registration(conn: sqlite3.Connection, enabled: bool) -> None:
    conn.execute("INSERT INTO settings (key, value) VALUES ('registration', ?) "
                 'ON CONFLICT (key) DO UPDATE SET value = excluded.value', ('1' if enabled else '0',))
