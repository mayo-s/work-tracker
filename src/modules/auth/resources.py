"""Login endpoints: /api/auth/status, /login, /logout, /first-user, /register, /me and /me/password."""

import datetime as dt
from collections.abc import Callable

import falcon
from spectree import Response

from src.models.users import User
from src.modules.auth.schemas import AuthStatus, LoginInput, NewUserInput, PasswordInput, ProfileInput, UserView
from src.modules.teams.schemas import TeamRef
from src.modules.auth.sessions import COOKIE, clear_session_cookie, set_session_cookie
from src.modules.storage.errors import ConflictError
from src.modules.storage.store import Storage, Store
from src.utils.spec import spec

TAGS = ['Login']
WRONG_LOGIN = 'Wrong username, e-mail address or password'
PAUSED = 'Too many attempts; try again in a minute'


class _AuthResource:
    def __init__(self, storage: Storage, clock: Callable[[], dt.datetime], enabled: bool = True) -> None:
        self._storage = storage
        self._clock = clock
        self._enabled = enabled

    def _log_in(self, req: falcon.Request, resp: falcon.Response, store: Store, user: User) -> None:
        set_session_cookie(req, resp, store.sessions().start(user.id, self._clock()))

    def _create(self, req: falcon.Request, resp: falcon.Response, store: Store, json: NewUserInput) -> None:
        """Add the user, log them in and answer with them (201)."""
        user = store.users(self._clock).add(json.to_user(), json.password)
        self._log_in(req, resp, store, user)
        resp.status = falcon.HTTP_201
        resp.media = UserView.of(user)


def _user_id(req: falcon.Request) -> str:
    user_id = req.context.get('user_id')
    if user_id is None:
        raise falcon.HTTPUnauthorized(title='401 Unauthorized', description='Log in first')
    return user_id


class AuthStatusResource(_AuthResource):
    @spec.validate(resp=Response(HTTP_200=AuthStatus), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Whether the login is on, whether a user exists, who is logged in (with their team and number of open
        invitations), and whether new users can register."""
        user_id = req.context.get('user_id') if self._enabled else None  # with the login off, nobody is logged in
        with self._storage.transaction() as store:
            users = store.users()
            status = AuthStatus(enabled=self._enabled, has_users=users.count() > 0, user=None,
                                registration=self._enabled and store.registration_open())
            if user_id is not None:
                membership = store.teams().membership(user_id)
                status.user = UserView.of(users.get(user_id))
                status.team = TeamRef.of(membership) if membership else None
                status.invitations = len(store.invitations().of_user(user_id))
            resp.media = status


class LoginResource(_AuthResource):
    @spec.validate(json=LoginInput, resp=Response('HTTP_401', 'HTTP_403', 'HTTP_429', HTTP_200=UserView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: LoginInput) -> None:
        """Log in with username or e-mail address; sets the session cookie (valid 24 h since the last activity).

        After 5 failed logins or registrations within a minute, logins pause (429). A deactivated user is refused (403).
        """
        with self._storage.transaction() as store:
            user = self._check(store, json)
            if user:
                self._log_in(req, resp, store, user)
        if user is None:  # answered after the transaction, so the failed login is stored
            raise falcon.HTTPUnauthorized(title='401 Unauthorized', description=WRONG_LOGIN)
        resp.media = UserView.of(user)

    def _check(self, store: Store, json: LoginInput) -> User | None:
        now = self._clock()
        attempts, users = store.attempts(), store.users()
        if attempts.paused(now):
            raise falcon.HTTPTooManyRequests(description=PAUSED)
        user = users.by_login(json.login)
        if user is None or not users.check_password(user.id, json.password):
            attempts.add(now)
            return None
        if not user.active:
            raise falcon.HTTPForbidden(description='This account is deactivated; ask an admin')
        attempts.clear_failed()
        return user


class LogoutResource(_AuthResource):
    @spec.validate(resp=Response('HTTP_204'), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Log out: ends the session and removes the cookie."""
        token = req.cookies.get(COOKIE)
        if token:
            with self._storage.transaction() as store:
                store.sessions().end(token)
        clear_session_cookie(resp)
        resp.status = falcon.HTTP_204


class FirstUserResource(_AuthResource):
    @spec.validate(json=NewUserInput, resp=Response('HTTP_409', HTTP_201=UserView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: NewUserInput) -> None:
        """Create the first user of a database that has none, and log in; refused (409) once a user exists."""
        with self._storage.transaction() as store:
            if store.users().count():
                raise ConflictError('A user exists already; log in instead')
            self._create(req, resp, store, json)


class RegisterResource(_AuthResource):
    @spec.validate(json=NewUserInput, resp=Response('HTTP_404', 'HTTP_409', 'HTTP_429', HTTP_201=UserView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: NewUserInput) -> None:
        """Register a new user and log in; the user then goes through the setup. Only while an admin has switched
        registration on (404 otherwise, and with the login off).

        Registrations count towards the pause after failed logins: after 5 within a minute, both pause (429).
        """
        with self._storage.transaction() as store:  # the attempt is kept even if the registration fails
            if not (self._enabled and store.registration_open()):
                raise falcon.HTTPNotFound(description='Registration is switched off')
            attempts = store.attempts()
            if attempts.paused(self._clock()):
                raise falcon.HTTPTooManyRequests(description=PAUSED)
            attempts.add(self._clock(), 'registration')
        with self._storage.transaction() as store:
            self._create(req, resp, store, json)


class MeResource(_AuthResource):
    @spec.validate(resp=Response('HTTP_401', HTTP_200=UserView), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """The logged-in user."""
        with self._storage.transaction() as store:
            resp.media = UserView.of(store.users().get(_user_id(req)))

    @spec.validate(json=ProfileInput, resp=Response('HTTP_401', 'HTTP_409', HTTP_200=UserView), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: ProfileInput) -> None:
        """Change username, e-mail address and name of the logged-in user."""
        with self._storage.transaction() as store:
            resp.media = UserView.of(store.users().update(json.to_user(_user_id(req))))


class PasswordResource(_AuthResource):
    @spec.validate(json=PasswordInput, resp=Response('HTTP_204', 'HTTP_401', 'HTTP_403'), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: PasswordInput) -> None:
        """Change the password: ends all sessions of the user and starts a new one for this browser."""
        user_id = _user_id(req)
        with self._storage.transaction() as store:
            users = store.users()
            if not users.check_password(user_id, json.current_password):
                raise falcon.HTTPForbidden(description='The current password is wrong')
            users.set_password(user_id, json.new_password)
            self._log_in(req, resp, store, users.get(user_id))
        resp.status = falcon.HTTP_204
