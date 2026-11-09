"""End-to-end tests: the app in the browser (Playwright, the installed Chrome) on a database with the test personas.

Run with `pytest -m e2e` after `npm run build`; the quick suite leaves them out. Each test gets its own database and
server, as in the app: login on, root and admins with two-factor login.
"""

import datetime as dt
import threading
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest

from src.__main__ import Server
from src.app import create_app
from src.lib.totp import code_at, time_step
from src.models.catalog import CODING, Service, new_activity_type
from src.models.entries import Entry
from src.models.teams import Team
from src.models.users import TwoFactor
from src.modules.storage.database import Database
from src.modules.storage.sqlite import SqliteStorage
from src.tests.users import HANS, KLARA, PASCAL, PASSWORD, RAINER

SECRET = 'JBSWY3DPEHPK3PXP'  # the authenticator of root and the admin


def seed(storage: SqliteStorage) -> dict[str, str]:
    """Klara: admin and member of Platform; Pascal: root; Hans: team admin of Platform, with an entry still without
    activity type; Rainer: not set up yet, invited to Platform. Returns their ids."""
    with storage.transaction() as store:
        users = store.users()
        ids = {'klara': users.add(KLARA, PASSWORD).id,
               'pascal': users.add(PASCAL.model_copy(update={'role': 'root'}), PASSWORD).id,
               'hans': users.add(HANS, PASSWORD).id, 'rainer': users.add(RAINER, PASSWORD).id}
        for name in ('klara', 'pascal'):
            users.save_two_factor(ids[name], TwoFactor(secret=SECRET, enabled=True))
        for name in ('klara', 'hans'):
            store.finish_setup(ids[name])
        team = store.teams().add(Team(name='Platform'))
        for name in ('hans', 'klara'):
            store.teams().join(ids[name], team.id)
        store.teams().set_team_role(ids['hans'], 'team_admin')
        store.team_services(team.id).add(Service(short_name='AUTH', name='auth-service'))
        store.invitations().invite(team.id, 'rainer.zufall@example.com', ids['hans'])
        store.activity_types(ids['hans']).add(new_activity_type(CODING))  # with tickets, Coding
        former = Entry(date=dt.date(2026, 10, 26), ticket_key='TNG-4347', duration=360, description='check permission')
        store.entries(ids['hans']).create(former)  # still without activity type (SPEC 4.6): for the review
    return ids


class _Quiet(WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def e2e_database(tmp_path, two_factor_required):
    database = Database(tmp_path / 'e2e.db')
    database.migrate()
    return database


@pytest.fixture
def people(e2e_database):
    """The personas' ids by username."""
    return seed(SqliteStorage(e2e_database))


@pytest.fixture
def base(e2e_database, people):
    """The app on a free port, served as `python -m src` serves it; its address."""
    server = make_server('127.0.0.1', 0, create_app(e2e_database, auth=True), server_class=Server, handler_class=_Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()


def code() -> str:
    """The current code of the seeded authenticator."""
    return code_at(SECRET, time_step(dt.datetime.now()))


@pytest.fixture
def logged_in(browser, base):
    """`logged_in('hans')`: a page in a browser context of its own (own cookies), logged in through the API."""
    contexts = []

    def open_page(name, color_scheme='dark'):
        context = browser.new_context(base_url=base, color_scheme=color_scheme)
        contexts.append(context)
        answer = context.request.post('/api/auth/login', data={'login': name, 'password': PASSWORD, 'code': code()})
        assert answer.status == 200, answer.text()
        return context.new_page()

    yield open_page
    for context in contexts:
        context.close()
