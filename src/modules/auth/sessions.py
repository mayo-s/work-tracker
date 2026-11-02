"""The session cookie and the middleware that lets only logged-in users in, except for the open paths."""

import datetime as dt
import os
from collections.abc import Callable
from typing import NamedTuple
from urllib.parse import quote

import falcon

from src.modules.storage.owners import NO_OWNER
from src.modules.storage.store import Storage
from src.modules.storage.users import SESSION_LIFETIME

COOKIE = 'wt_session'
PAUSED = 'Too many attempts; try again in a minute'
OPEN_PATHS = {
    '/login', '/register', '/health', '/api/auth/status', '/api/auth/login', '/api/auth/logout', '/api/auth/root',
    '/api/auth/root/reset', '/api/auth/register',
}
OPEN_PREFIXES = ('/static/', '/apidoc')
# After a one-time password, until the user chose their own: only this page, its API and what every page needs
NEW_PASSWORD_PATHS = {'/password', '/api/auth/me/password'}
# Root tracks no work: its pages and the API behind them; other pages forward to /admin, the rest of the API answers 403
ROOT_PAGES = {'/admin', '/settings', '/password'}
ROOT_API = ('/api/auth/', '/api/admin/', '/api/theme')


def auth_enabled() -> bool:
    """The login is on unless switched off for local development with WORK_TRACKER_AUTH=off."""
    return os.environ.get('WORK_TRACKER_AUTH', 'on').lower() != 'off'


def current_user(req: falcon.Request) -> str:
    """The user whose data a request works on: the logged-in user (or, with the login off, the first user who is not
    root)."""
    user_id = req.context.get('user_id')
    if user_id is None:
        raise falcon.HTTPUnauthorized(title='401 Unauthorized', description='Log in first')
    return user_id


def set_session_cookie(req: falcon.Request, resp: falcon.Response, token: str) -> None:
    https = req.scheme == 'https' or req.get_header('X-Forwarded-Proto') == 'https'
    resp.set_cookie(COOKIE, token, max_age=int(SESSION_LIFETIME.total_seconds()), path='/', secure=https,
                    http_only=True, same_site='Strict')


def clear_session_cookie(resp: falcon.Response) -> None:
    resp.unset_cookie(COOKIE, path='/', same_site='Strict')


class Authentication:
    """Middleware: `req.context.user_id` for a valid session (renewing the cookie with the session); without one,
    pages forward to `/login?next=…` and the API answers 401. Until root exists, a new database creates it on
    /setup, an existing one on /login. After a one-time password, pages forward to /password and the API answers 403
    until the user chose their own. Root only reaches its pages (ROOT_PAGES) and their API."""

    def __init__(self, storage: Storage, clock: Callable[[], dt.datetime]) -> None:
        self._storage = storage
        self._clock = clock

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        token = req.cookies.get(COOKIE)
        with self._storage.transaction() as store:
            user_id, renewed = store.sessions().user_id(token, self._clock()) if token else (None, False)
            user = store.users().get(user_id) if user_id is not None else None
            access = _Access(user_id, not store.users().count(), store.setup_done(NO_OWNER),
                             user is not None and user.must_change_password, user is not None and user.role == 'root')
        req.context.user_id = user_id
        if renewed:
            set_session_cookie(req, resp, token)
        _check(req, access)


class _Access(NamedTuple):
    user_id: str | None
    first_user_missing: bool
    set_up: bool  # the database (not logged in) or the user
    new_password: bool  # a one-time password, still to replace
    root: bool


def _check(req: falcon.Request, access: _Access) -> None:
    """Without a session, only what is open; after a one-time password, only the page to choose a new one; root only
    its own pages."""
    if access.user_id is None:
        allowed, refuse = _open(req.path, access.first_user_missing, access.set_up), _refuse
    elif access.new_password:
        allowed, refuse = _open_until_new_password(req.path), _ask_for_new_password
    else:
        allowed, refuse = not access.root or _open_to_root(req.path), _send_root_to_admin
    if not allowed:
        refuse(req)


def _open(path: str, first_user_missing: bool, set_up: bool) -> bool:
    if path in OPEN_PATHS or path.startswith(OPEN_PREFIXES):
        return True
    return first_user_missing and not set_up and not path.startswith('/api/')  # pages forward to /setup, creating root


def _open_to_root(path: str) -> bool:
    return path in OPEN_PATHS | ROOT_PAGES or path.startswith(OPEN_PREFIXES + ROOT_API)


def _send_root_to_admin(req: falcon.Request) -> None:
    if req.path.startswith('/api/'):
        raise falcon.HTTPForbidden(description='Root runs the app and tracks no work')
    raise falcon.HTTPSeeOther('/admin')


def _open_until_new_password(path: str) -> bool:
    return path in OPEN_PATHS | NEW_PASSWORD_PATHS or path.startswith(OPEN_PREFIXES)


def _ask_for_new_password(req: falcon.Request) -> None:
    if req.path.startswith('/api/'):
        raise falcon.HTTPForbidden(description='Choose your own password first, on /password')
    raise falcon.HTTPSeeOther('/password')


def _refuse(req: falcon.Request) -> None:
    if req.path.startswith('/api/'):
        raise falcon.HTTPUnauthorized(title='401 Unauthorized', description='Log in first')
    raise falcon.HTTPSeeOther(f'/login?next={quote(req.relative_uri, safe="")}')


class LocalUser:
    """Middleware with the login off (local development): every request works on the data of the first user who is
    not root, or on the data without an owner while there is none yet."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        with self._storage.transaction() as store:
            first = store.users().first_id()
        req.context.user_id = NO_OWNER if first is None else first
