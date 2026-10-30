"""Settings endpoints: /api/settings and /api/theme."""

import falcon
from spectree import Response

from src.modules.auth.sessions import current_user
from src.modules.storage.store import Storage
from src.modules.settings.schemas import SettingsView, ThemeView
from src.utils.spec import spec

TAGS = ['Settings']


class SettingsResource:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response(HTTP_200=SettingsView), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Start date and opening balance of the overtime balance."""
        with self._storage.transaction() as store:
            resp.media = SettingsView.of(store.load_settings(current_user(req)))

    @spec.validate(json=SettingsView, resp=Response(HTTP_200=SettingsView), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: SettingsView) -> None:
        """Change the start date and opening balance; reports count from the new start day on."""
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
