"""The session cookie and the middleware that lets only logged-in users in, except for the open paths."""

import datetime as dt
import os
from collections.abc import Callable
from urllib.parse import quote

import falcon

from src.modules.storage.database import Database
from src.modules.storage.settings import setup_done
from src.modules.storage.users import SESSION_LIFETIME, SessionRepository, UserRepository

COOKIE = 'wt_session'
OPEN_PATHS = {'/login', '/health', '/api/auth/status', '/api/auth/login', '/api/auth/logout', '/api/auth/first-user'}
OPEN_PREFIXES = ('/static/', '/apidoc')


def auth_enabled() -> bool:
    """The login is on unless switched off for local development with WORK_TRACKER_AUTH=off."""
    return os.environ.get('WORK_TRACKER_AUTH', 'on').lower() != 'off'


def set_session_cookie(req: falcon.Request, resp: falcon.Response, token: str) -> None:
    https = req.scheme == 'https' or req.get_header('X-Forwarded-Proto') == 'https'
    resp.set_cookie(COOKIE, token, max_age=int(SESSION_LIFETIME.total_seconds()), path='/', secure=https,
                    http_only=True, same_site='Strict')


def clear_session_cookie(resp: falcon.Response) -> None:
    resp.unset_cookie(COOKIE, path='/', same_site='Strict')


class Authentication:
    """Middleware: `req.context.user_id` for a valid session (renewing the cookie with the session); without one,
    pages forward to `/login?next=…` and the API answers 401. Until the first user exists, a new database is set up
    on /setup (which creates it), an existing one gets it on /login."""

    def __init__(self, database: Database, clock: Callable[[], dt.datetime]) -> None:
        self._database = database
        self._clock = clock

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        token = req.cookies.get(COOKIE)
        with self._database.transaction() as conn:
            user_id, renewed = SessionRepository(conn).user_id(token, self._clock()) if token else (None, False)
            first_user_missing = not UserRepository(conn).count()
            set_up = setup_done(conn)
        req.context.user_id = user_id
        if renewed:
            set_session_cookie(req, resp, token)
        if user_id is None and not _open(req.path, first_user_missing, set_up):
            _refuse(req)


def _open(path: str, first_user_missing: bool, set_up: bool) -> bool:
    if path in OPEN_PATHS or path.startswith(OPEN_PREFIXES):
        return True
    if first_user_missing and not set_up:  # the setup creates the first user
        return not path.startswith('/api/') or path == '/api/setup'
    return False


def _refuse(req: falcon.Request) -> None:
    if req.path.startswith('/api/'):
        raise falcon.HTTPUnauthorized(title='401 Unauthorized', description='Log in first')
    raise falcon.HTTPSeeOther(f'/login?next={quote(req.relative_uri, safe="")}')
