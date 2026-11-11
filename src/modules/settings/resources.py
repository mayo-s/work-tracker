"""Settings endpoints: /api/settings, /api/theme and /api/language."""

import falcon
from spectree import Response

from src.modules.auth.sessions import current_user
from src.modules.pages.languages import set_language_cookie
from src.modules.storage.store import Storage
from src.modules.settings.schemas import LanguageView, SettingsView, ThemeView
from src.utils.spec import spec

TAGS = ['Settings']


class SettingsResource:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response(HTTP_200=SettingsView), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Start date and opening balance of the overtime balance, and the way of working."""
        with self._storage.transaction() as store:
            resp.media = SettingsView.of(store.load_settings(current_user(req)))

    @spec.validate(json=SettingsView, resp=Response(HTTP_200=SettingsView), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: SettingsView) -> None:
        """Change the settings; reports count from the new start day on, and the pages follow the way of working."""
        with self._storage.transaction() as store:
            store.save_settings(current_user(req), json.to_settings())
            resp.media = SettingsView.of(store.load_settings(current_user(req)))


class ThemeResource:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response(HTTP_200=ThemeView), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """The color theme of all pages."""
        with self._storage.transaction() as store:
            resp.media = ThemeView(theme=store.load_theme(current_user(req)))

    @spec.validate(json=ThemeView, resp=Response(HTTP_200=ThemeView), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: ThemeView) -> None:
        """Choose the color theme: system, light or dark."""
        with self._storage.transaction() as store:
            store.save_theme(current_user(req), json.theme)
        resp.media = json


class LanguageResource:
    """Open to everyone (SPEC 5.16): the pages before the login switch the language too."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(json=LanguageView, resp=Response(HTTP_200=LanguageView), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: LanguageView) -> None:
        """Choose the UI language of all pages: kept in this browser (a cookie, also before the login) and, logged in,
        in the account, so it follows the user to other devices."""
        user_id = req.context.get('user_id')
        if user_id is not None:
            with self._storage.transaction() as store:
                store.save_language(user_id, json.language)
        set_language_cookie(req, resp, json.language)
        resp.media = json
