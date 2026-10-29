"""Login endpoints: /api/auth/status, /login, /logout, /first-user, /me and /me/password."""

import datetime as dt
import sqlite3
from collections.abc import Callable

import falcon
from spectree import Response

from src.models.users import User
from src.modules.auth.schemas import AuthStatus, LoginInput, NewUserInput, PasswordInput, ProfileInput, UserView
from src.modules.auth.sessions import COOKIE, clear_session_cookie, set_session_cookie
from src.modules.storage.database import Database
from src.modules.storage.errors import ConflictError
from src.modules.storage.users import FailedLogins, SessionRepository, UserRepository
from src.utils.spec import spec

TAGS = ['Login']
WRONG_LOGIN = 'Wrong username, e-mail address or password'


class _AuthResource:
    def __init__(self, database: Database, clock: Callable[[], dt.datetime], enabled: bool = True) -> None:
        self._database = database
        self._clock = clock
        self._enabled = enabled

    def _log_in(self, req: falcon.Request, resp: falcon.Response, conn: sqlite3.Connection, user: User) -> None:
        set_session_cookie(req, resp, SessionRepository(conn).start(user.id, self._clock()))


def _user_id(req: falcon.Request) -> int:
    user_id = req.context.get('user_id')
    if user_id is None:
        raise falcon.HTTPUnauthorized(title='401 Unauthorized', description='Log in first')
    return user_id


class AuthStatusResource(_AuthResource):
    @spec.validate(resp=Response(HTTP_200=AuthStatus), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Whether the login is on, whether a user exists, and who is logged in."""
        user_id = req.context.get('user_id')
        with self._database.transaction() as conn:
            users = UserRepository(conn)
            user = UserView.of(users.get(user_id)) if user_id is not None else None
            resp.media = AuthStatus(enabled=self._enabled, has_users=users.count() > 0, user=user)


class LoginResource(_AuthResource):
    @spec.validate(json=LoginInput, resp=Response('HTTP_401', 'HTTP_429', HTTP_200=UserView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: LoginInput) -> None:
        """Log in with username or e-mail address; sets the session cookie (valid 24 h since the last activity).

        After 5 failed logins within a minute, logins pause (429).
        """
        with self._database.transaction() as conn:
            user = self._check(conn, json)
            if user:
                self._log_in(req, resp, conn, user)
        if user is None:  # answered after the transaction, so the failed login is stored
            raise falcon.HTTPUnauthorized(title='401 Unauthorized', description=WRONG_LOGIN)
        resp.media = UserView.of(user)

    def _check(self, conn: sqlite3.Connection, json: LoginInput) -> User | None:
        now = self._clock()
        failed, users = FailedLogins(conn), UserRepository(conn)
        if failed.paused(now):
            raise falcon.HTTPTooManyRequests(description='Too many failed logins; try again in a minute')
        user = users.by_login(json.login)
        if user is None or not users.check_password(user.id, json.password):
            failed.add(now)
            return None
        failed.clear()
        return user


class LogoutResource(_AuthResource):
    @spec.validate(resp=Response('HTTP_204'), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Log out: ends the session and removes the cookie."""
        token = req.cookies.get(COOKIE)
        if token:
            with self._database.transaction() as conn:
                SessionRepository(conn).end(token)
        clear_session_cookie(resp)
        resp.status = falcon.HTTP_204


class FirstUserResource(_AuthResource):
    @spec.validate(json=NewUserInput, resp=Response('HTTP_409', HTTP_201=UserView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: NewUserInput) -> None:
        """Create the first user of a database that has none, and log in; refused (409) once a user exists."""
        with self._database.transaction() as conn:
            users = UserRepository(conn)
            if users.count():
                raise ConflictError('A user exists already; log in instead')
            user = users.add(json.to_user(), json.password)
            self._log_in(req, resp, conn, user)
        resp.status = falcon.HTTP_201
        resp.media = UserView.of(user)


class MeResource(_AuthResource):
    @spec.validate(resp=Response('HTTP_401', HTTP_200=UserView), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """The logged-in user."""
        with self._database.transaction() as conn:
            resp.media = UserView.of(UserRepository(conn).get(_user_id(req)))

    @spec.validate(json=ProfileInput, resp=Response('HTTP_401', 'HTTP_409', HTTP_200=UserView), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: ProfileInput) -> None:
        """Change username, e-mail address and name of the logged-in user."""
        with self._database.transaction() as conn:
            resp.media = UserView.of(UserRepository(conn).update(json.to_user(_user_id(req))))


class PasswordResource(_AuthResource):
    @spec.validate(json=PasswordInput, resp=Response('HTTP_204', 'HTTP_401', 'HTTP_403'), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: PasswordInput) -> None:
        """Change the password: ends all sessions of the user and starts a new one for this browser."""
        user_id = _user_id(req)
        with self._database.transaction() as conn:
            users = UserRepository(conn)
            if not users.check_password(user_id, json.current_password):
                raise falcon.HTTPForbidden(description='The current password is wrong')
            users.set_password(user_id, json.new_password)
            self._log_in(req, resp, conn, users.get(user_id))
        resp.status = falcon.HTTP_204
