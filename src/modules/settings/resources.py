"""Settings endpoint: /api/settings."""

import falcon
from spectree import Response

from src.modules.settings.schemas import SettingsView
from src.modules.storage.database import Database
from src.modules.storage.settings import load_settings, save_settings
from src.utils.spec import spec

TAGS = ['Settings']


class SettingsResource:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response(HTTP_200=SettingsView), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Start date and opening balance of the overtime balance."""
        with self._database.transaction() as conn:
            resp.media = SettingsView.of(load_settings(conn))

    @spec.validate(json=SettingsView, resp=Response(HTTP_200=SettingsView), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: SettingsView) -> None:
        """Change the start date and opening balance; reports count from the new start day on."""
        with self._database.transaction() as conn:
            save_settings(conn, json.to_settings())
            resp.media = SettingsView.of(load_settings(conn))
