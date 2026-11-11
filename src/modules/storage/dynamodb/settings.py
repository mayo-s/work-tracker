"""A user's settings (balance, way of working, setup, theme, language) in their partition's `SETTINGS` item; app-wide
ones."""

import datetime as dt
from typing import Any, get_args

from src.models.settings import Settings
from src.modules.storage.dynamodb.keys import APP, SETTINGS, user_partition
from src.modules.storage.dynamodb.table import Item
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.store import Language, Theme


def _values(unit: Unit, pk: str) -> Item:
    return unit.get(pk, SETTINGS) or {'PK': pk, 'SK': SETTINGS}


def _save(unit: Unit, pk: str, **values: Any) -> None:
    unit.put(_values(unit, pk) | values)


def load_settings(unit: Unit, user_id: str) -> Settings:
    """The user's balance start, opening balance and way of working; before the setup: today, 0:00 and tickets."""
    values = _values(unit, user_partition(user_id))
    return Settings(balance_start=values.get('balance_start', dt.date.today().isoformat()),
                    opening_balance=int(values.get('opening_balance', 0)), work_mode=values.get('work_mode', 'tickets'))


def save_settings(unit: Unit, user_id: str, settings: Settings) -> None:
    _save(unit, user_partition(user_id), balance_start=settings.balance_start.isoformat(),
          opening_balance=settings.opening_balance, work_mode=settings.work_mode)


def setup_done(unit: Unit, user_id: str) -> bool:
    """False until the user finished the setup (/setup)."""
    return bool(_values(unit, user_partition(user_id)).get('setup_done'))


def finish_setup(unit: Unit, user_id: str) -> None:
    """The setup is done, also an import that was started for it."""
    _save(unit, user_partition(user_id), setup_done=True, import_unfinished=False)


def start_import(unit: Unit, user_id: str) -> None:
    """An import of an export file has started; until the setup is done, importing again replaces what it wrote."""
    _save(unit, user_partition(user_id), import_unfinished=True)


def import_unfinished(unit: Unit, user_id: str) -> bool:
    return bool(_values(unit, user_partition(user_id)).get('import_unfinished'))


def load_theme(unit: Unit, user_id: str) -> Theme:
    """The chosen color theme; `system` follows the system setting."""
    theme = _values(unit, user_partition(user_id)).get('theme', 'system')
    return theme if theme in get_args(Theme) else 'system'


def save_theme(unit: Unit, user_id: str, theme: Theme) -> None:
    _save(unit, user_partition(user_id), theme=theme)


def load_language(unit: Unit, user_id: str) -> Language | None:
    """The chosen UI language; None until one is chosen (then the browser's applies)."""
    language = _values(unit, user_partition(user_id)).get('language')
    return language if language in get_args(Language) else None


def save_language(unit: Unit, user_id: str, language: Language) -> None:
    _save(unit, user_partition(user_id), language=language)


def registration_open(unit: Unit) -> bool:
    """Whether new users can register on /register (app-wide; off until an admin switches it on)."""
    return bool(_values(unit, APP).get('registration'))


def set_registration(unit: Unit, enabled: bool) -> None:
    _save(unit, APP, registration=enabled)


def start_restore(unit: Unit) -> None:
    """A full restore has begun: until it finishes (it may take several requests), only root uses the app."""
    _save(unit, APP, restore_unfinished=True)


def restore_unfinished(unit: Unit) -> bool:
    return bool(_values(unit, APP).get('restore_unfinished'))


def finish_restore(unit: Unit) -> None:
    _save(unit, APP, restore_unfinished=False)
