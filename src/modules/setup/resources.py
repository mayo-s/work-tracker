"""Initial setup endpoint: /api/setup (status, and saving the whole setup at once)."""

import datetime as dt
import sqlite3
from collections.abc import Callable

import falcon
from spectree import Response

from src.modules.auth.sessions import set_session_cookie

from src.modules.setup.schemas import SetupInput, SetupStatus
from src.modules.storage.catalog import ServiceRepository
from src.modules.storage.database import Database
from src.modules.storage.errors import ConflictError
from src.modules.storage.pto_years import PtoYearRepository
from src.modules.storage.schedules import ScheduleRepository
from src.modules.storage.settings import finish_setup, save_settings, setup_done
from src.modules.storage.users import SessionRepository, UserRepository
from src.utils.spec import spec

TAGS = ['Setup']


class SetupResource:
    def __init__(self, database: Database, clock: Callable[[], dt.datetime] = dt.datetime.now) -> None:
        self._database = database
        self._clock = clock

    @spec.validate(resp=Response(HTTP_200=SetupStatus), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Whether the database is set up; until then, pages forward to /setup."""
        with self._database.transaction() as conn:
            resp.media = SetupStatus(done=setup_done(conn))

    @spec.validate(json=SetupInput, resp=Response('HTTP_409', HTTP_200=SetupStatus), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: SetupInput) -> None:
        """Set up a new database at once: the first user, start day, opening balance, work schedule, PTO years and
        services; the new user is logged in.

        The schedule applies from the start day; PTO is entered for the first year and the year after. Refused (409)
        once the database is set up: then the settings page changes everything.
        """
        with self._database.transaction() as conn:
            if setup_done(conn):
                raise ConflictError('The database is already set up; change the settings on /settings')
            self._first_user(req, resp, conn, json)
            save_settings(conn, json.settings())
            ScheduleRepository(conn).replace_all(json.schedule.starting(json.balance_start).to_schedule())
            PtoYearRepository(conn).replace_all(json.pto_years())
            services = ServiceRepository(conn)
            for service in json.service_models():
                services.add(service)
            finish_setup(conn)
        resp.media = SetupStatus(done=True)

    def _first_user(self, req: falcon.Request, resp: falcon.Response, conn: sqlite3.Connection, json: SetupInput) -> None:
        """The setup creates the first user and logs in; a database that already has a user keeps it."""
        users = UserRepository(conn)
        if users.count():
            if json.user:
                raise ConflictError('A user exists already; leave out the user')
            return
        if not json.user:
            raise ConflictError('The setup creates the first user: enter username, e-mail address, name and password')
        user = users.add(json.user.to_user(), json.user.password)
        set_session_cookie(req, resp, SessionRepository(conn).start(user.id, self._clock()))
