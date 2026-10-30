"""A user's settings (balance, setup, theme) in the `SETTINGS` item of their partition, and the app-wide ones."""

import datetime as dt
from typing import Any, get_args

from src.models.settings import Settings
from src.modules.storage.dynamodb.keys import APP, SETTINGS, user_partition
from src.modules.storage.dynamodb.table import Item
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.store import Theme


def _values(unit: Unit, pk: str) -> Item:
    return unit.get(pk, SETTINGS) or {'PK': pk, 'SK': SETTINGS}


def _save(unit: Unit, pk: str, **values: Any) -> None:
    unit.put(_values(unit, pk) | values)


def load_settings(unit: Unit, user_id: str) -> Settings:
    """The user's balance start and opening balance; before the setup: today and 0:00."""
    values = _values(unit, user_partition(user_id))
    return Settings(balance_start=values.get('balance_start', dt.date.today().isoformat()),
                    opening_balance=int(values.get('opening_balance', 0)))


def save_settings(unit: Unit, user_id: str, settings: Settings) -> None:
    _save(unit, user_partition(user_id), balance_start=settings.balance_start.isoformat(),
          opening_balance=settings.opening_balance)


def setup_done(unit: Unit, user_id: str) -> bool:
    """False until the user finished the setup (/setup)."""
    return bool(_values(unit, user_partition(user_id)).get('setup_done'))


def finish_setup(unit: Unit, user_id: str) -> None:
    _save(unit, user_partition(user_id), setup_done=True)


def load_theme(unit: Unit, user_id: str) -> Theme:
    """The chosen color theme; `system` follows the system setting."""
    theme = _values(unit, user_partition(user_id)).get('theme', 'system')
    return theme if theme in get_args(Theme) else 'system'


def save_theme(unit: Unit, user_id: str, theme: Theme) -> None:
    _save(unit, user_partition(user_id), theme=theme)


def registration_open(unit: Unit) -> bool:
    """Whether new users can register on /register (app-wide; off until an admin switches it on)."""
    return bool(_values(unit, APP).get('registration'))


def set_registration(unit: Unit, enabled: bool) -> None:
    _save(unit, APP, registration=enabled)
