"""Initial setup endpoints: /api/setup (status, and saving the whole setup at once) and /api/setup/import (from an
export file)."""

import falcon
from spectree import Response

from src.lib.texts import text
from src.models.catalog import CODING, new_activity_type
from src.modules.auth.sessions import current_user
from src.modules.setup.schemas import SetupImportInput, SetupInput, SetupStatus
from src.modules.storage.errors import ConflictError
from src.modules.storage.owners import NO_OWNER
from src.modules.storage.store import Storage, Store
from src.modules.userdata.importing import import_data
from src.modules.userdata.schemas import ImportSummary
from src.utils.spec import spec

TAGS = ['Setup']


class SetupResource:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response(HTTP_200=SetupStatus), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Whether the user's data is set up (not logged in: a new database's); until then, pages forward to /setup."""
        user_id = req.context.get('user_id')
        with self._storage.transaction() as store:
            resp.media = SetupStatus(done=store.setup_done(NO_OWNER if user_id is None else user_id))

    @spec.validate(json=SetupInput, resp=Response('HTTP_409', HTTP_200=SetupStatus), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: SetupInput) -> None:
        """Set up the logged-in user's data at once: start day, opening balance, way of working, work schedule, PTO
        years and services; with tickets, the activity type Coding too if asked for.

        The schedule applies from the start day; PTO is entered for the first year and the year after. Refused (409)
        once set up: then the settings page changes everything.
        """
        with self._storage.transaction() as store:
            user_id = _user_to_set_up(req, store)
            store.save_settings(user_id, json.settings())
            store.schedules(user_id).replace_all(json.schedule.starting(json.balance_start).to_schedule())
            store.pto_years(user_id).replace_all(json.pto_years())
            services = store.services(user_id)
            for service in json.service_models():
                services.add(service)
            if json.work_mode == 'tickets' and json.coding:
                store.activity_types(user_id).add(new_activity_type(CODING))
            store.finish_setup(user_id)
        resp.media = SetupStatus(done=True)


class SetupImportResource:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(json=SetupImportInput, resp=Response('HTTP_409', HTTP_200=ImportSummary), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: SetupImportInput) -> None:
        """Set up the logged-in user's data from an export file instead of the setup steps; answers how many records of
        each type it wrote.

        Only for a user who is not set up and has no days or entries (409 otherwise). Everything is written or nothing:
        another format, a newer version (422) or a file referring to records it does not hold (409) leave no trace.
        """
        with self._storage.transaction() as store:
            user_id = _user_to_set_up(req, store)
            resp.media = import_data(store, user_id, json.data)
            store.finish_setup(user_id)


def _user_to_set_up(req: falcon.Request, store: Store) -> str:
    """The current user; refused once set up."""
    user_id = current_user(req)
    if store.setup_done(user_id):
        raise ConflictError(text('Already set up; change the settings on /settings'))
    return user_id
