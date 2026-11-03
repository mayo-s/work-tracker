"""Login endpoints: /api/auth/status, /login, /logout, /root, /root/reset, /register, /me, /me/password, /me/audit and
/me/two-factor (also /off, /recovery and /new-app)."""

import datetime as dt
from collections.abc import Callable

import falcon
from spectree import Response

from src.lib.totp import new_secret, provisioning_uri
from src.models.users import Role, TwoFactor, User
from src.modules.admin.audit import AuditView, record
from src.modules.auth.schemas import (
    AuthStatus, LoginInput, NewAppInput, NewUserInput, PasswordInput, ProfileInput, RecoveryCodes, RootInput, RootResetInput,
    TwoFactorCode, TwoFactorOff, TwoFactorSetup, TwoFactorStatus, UserView,
)
from src.modules.teams.schemas import TeamRef
from src.modules.auth.sessions import (
    BROWSER_COOKIE, COOKIE, PAUSED, clear_session_cookie, set_browser_cookie, set_session_cookie,
)
from src.modules.auth.setup_token import SetupToken, check_setup_token
from src.modules.auth.two_factor import (
    WRONG_CODE, code_accepted, code_or_recovery_accepted, new_app_accepted, new_recovery_codes, qr_code, recovery_hash,
    required, second_factor,
)
from src.modules.storage.errors import ConflictError
from src.modules.storage.store import Storage, Store
from src.modules.storage.users import session_lifetime
from src.utils.spec import spec

TAGS = ['Login']
WRONG_LOGIN = 'Wrong username, e-mail address or password'
ROOT_EXISTS = 'There is a root already; log in instead'


class _AuthResource:
    def __init__(self, storage: Storage, clock: Callable[[], dt.datetime], enabled: bool = True,
                 setup_token: SetupToken | None = None) -> None:
        self._storage = storage
        self._clock = clock
        self._enabled = enabled
        self._setup_token = setup_token

    def _log_in(self, req: falcon.Request, resp: falcon.Response, store: Store, user: User) -> None:
        set_session_cookie(req, resp, store.sessions().start(user.id, self._clock()), session_lifetime(user.role))

    def _create(self, req: falcon.Request, resp: falcon.Response, store: Store, json: NewUserInput, role: Role = 'user',
                ) -> User:
        """Add the user, log them in and answer with them (201)."""
        user = store.users(self._clock).add(json.to_user().model_copy(update={'role': role}), json.password)
        self._log_in(req, resp, store, user)
        resp.status = falcon.HTTP_201
        resp.media = UserView.of(user)
        return user

    def _refuse_if_root(self, exists: bool) -> None:
        """409 if there is a root (`exists`), or if there is none."""
        with self._storage.transaction() as store:
            if (store.users().root_id() is not None) == exists:
                raise ConflictError(ROOT_EXISTS if exists else 'There is no root yet; create it first')


def _user_id(req: falcon.Request) -> str:
    user_id = req.context.get('user_id')
    if user_id is None:
        raise falcon.HTTPUnauthorized(title='401 Unauthorized', description='Log in first')
    return user_id


class AuthStatusResource(_AuthResource):
    @spec.validate(resp=Response(HTTP_200=AuthStatus), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Whether the login is on, whether users and root exist, who is logged in (with their team and number of open
        invitations), whether new users can register, and whether creating root needs the setup token."""
        user_id = req.context.get('user_id') if self._enabled else None  # with the login off, nobody is logged in
        with self._storage.transaction() as store:
            status = self._status(store)
            resp.media = _with_user(status, store, user_id) if user_id is not None else status

    def _status(self, store: Store) -> AuthStatus:
        users, token = store.users(), self._setup_token is not None
        has_root = users.root_id() is not None
        return AuthStatus(enabled=self._enabled, has_users=users.count() > 0, has_root=has_root, user=None,
                          registration=self._enabled and store.registration_open(), setup_token=token and not has_root,
                          root_reset=token and has_root)


def _with_user(status: AuthStatus, store: Store, user_id: str) -> AuthStatus:
    """The logged-in user, with their team and number of open invitations."""
    membership = store.teams().membership(user_id)
    return status.model_copy(update={'user': UserView.of(store.users().get(user_id)),
                                     'team': TeamRef.of(membership) if membership else None,
                                     'invitations': len(store.invitations().of_user(user_id))})


class LoginResource(_AuthResource):
    @spec.validate(json=LoginInput, resp=Response('HTTP_401', 'HTTP_403', 'HTTP_429', HTTP_200=UserView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: LoginInput) -> None:
        """Log in with username or e-mail address; sets the session cookie (valid 24 h since the last activity).

        After 5 failed logins or registrations within a minute, logins pause (429). A deactivated user is refused (403).
        With two-factor login, the right password without `code` answers 401 with the code `two_factor_required`
        (not counted as failed); a wrong code counts as a failed login. With `remember` and a code, the browser needs
        no code for 30 days (its own cookie; not for root).
        """
        with self._storage.transaction() as store:
            user, refusal = self._check(store, json, req.cookies.get(BROWSER_COOKIE))
            if user:
                self._log_in(req, resp, store, user)
                self._remember(req, resp, store, user, json)
        if refusal:  # answered after the transaction, so the failed login is stored
            raise falcon.HTTPUnauthorized(title='401 Unauthorized', description=refusal)
        resp.media = UserView.of(user)

    def _remember(self, req: falcon.Request, resp: falcon.Response, store: Store, user: User, json: LoginInput) -> None:
        """With `remember` and a code: the browser needs no code for 30 days; not for root."""
        if json.remember and json.code and user.two_factor and user.role != 'root':
            set_browser_cookie(req, resp, store.browsers().remember(user.id, self._clock()))

    def _check(self, store: Store, json: LoginInput, browser: str | None) -> tuple[User | None, str | None]:
        """The user, or why the login failed (counted as a failed login)."""
        now = self._clock()
        attempts, users = store.attempts(), store.users()
        if attempts.paused(now):
            raise falcon.HTTPTooManyRequests(description=PAUSED)
        user = users.by_login(json.login)
        if user is None or not users.check_password(user.id, json.password):
            attempts.add(now)
            return None, WRONG_LOGIN
        if not user.active:
            raise falcon.HTTPForbidden(description='This account is deactivated; ask an admin')
        if not second_factor(store, user, json.code, now, browser):
            attempts.add(now)
            return None, WRONG_CODE
        attempts.clear_failed(now)
        return user, None


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


class RootResource(_AuthResource):
    @spec.validate(json=RootInput, resp=Response('HTTP_403', 'HTTP_409', 'HTTP_429', HTTP_201=UserView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: RootInput) -> None:
        """Create root, who runs the app and tracks no work, and log in: once per database (409 afterwards), on a new
        one or one with users. On AWS Lambda only with the setup token (403 if wrong; wrong tokens count as failed
        logins), which then works no more (409 a second time)."""
        self._refuse_if_root(True)
        used = check_setup_token(self._storage, self._setup_token, json.setup_token, self._clock)
        with self._storage.transaction() as store:
            if store.users().root_id():
                raise ConflictError(ROOT_EXISTS)
            root = self._create(req, resp, store, json, 'root')
            _use(store, used, self._clock())
            record(store, self._clock(), root.id, 'root_created', root.id)


def _use(store: Store, token_hash: str | None, now: dt.datetime) -> None:
    if token_hash:
        store.use_setup_token(token_hash, now)


class RootResetResource(_AuthResource):
    @spec.validate(json=RootResetInput, resp=Response('HTTP_403', 'HTTP_409', 'HTTP_429', HTTP_200=UserView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: RootResetInput) -> None:
        """Reset root's login with a new setup token (AWS Lambda; root forgot its password or lost its authenticator
        app): a new password, two-factor login off until set up again (required), all of root's sessions end, and
        root is logged in. The token then works no more (409 a second time); 403 if wrong
        (counts as a failed login). Locally there is no setup token (409): use the set-password command."""
        if self._setup_token is None:
            raise ConflictError('No setup token here; locally, reset the password with the set-password command')
        self._refuse_if_root(False)
        used = check_setup_token(self._storage, self._setup_token, json.setup_token, self._clock)
        with self._storage.transaction() as store:
            users, now = store.users(), self._clock()
            root_id = users.root_id()
            users.set_password(root_id, json.new_password)
            users.save_two_factor(root_id, None)  # set up again right after, with a new authenticator app
            _use(store, used, now)
            record(store, now, root_id, 'root_login_reset', root_id)
            self._log_in(req, resp, store, users.get(root_id))
            resp.media = UserView.of(users.get(root_id))


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


class MyAuditResource(_AuthResource):
    @spec.validate(resp=Response('HTTP_401', HTTP_200=list[AuditView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """The latest changes to the logged-in user's account (from the audit log), newest first."""
        with self._storage.transaction() as store:
            resp.media = [AuditView.of(entry) for entry in store.audit_log().of_user(_user_id(req))]


class TwoFactorResource(_AuthResource):
    @spec.validate(resp=Response('HTTP_401', HTTP_200=TwoFactorStatus), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Whether the logged-in user's login needs a code of an authenticator app, whether it must (root and admins),
        and how many recovery codes are left."""
        with self._storage.transaction() as store:
            users = store.users()
            user, state = users.get(_user_id(req)), users.two_factor(_user_id(req))
            resp.media = TwoFactorStatus(enabled=user.two_factor, required=required(user),
                                         recovery_left=len(state.recovery) if state and state.enabled else 0)

    @spec.validate(resp=Response('HTTP_401', 'HTTP_409', HTTP_201=TwoFactorSetup), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Start setting up two-factor login: a new secret, as QR code and as text, for the authenticator app; a first
        code confirms it (PUT). Starting again replaces an unconfirmed secret; 409 once it is on."""
        with self._storage.transaction() as store:
            users = store.users()
            user = users.get(_user_id(req))
            if user.two_factor:
                raise ConflictError('Two-factor login is on already')
            secret = new_secret()
            users.save_two_factor(user.id, TwoFactor(secret=secret))
        resp.status = falcon.HTTP_201
        resp.media = _setup(secret, user.username)

    @spec.validate(json=TwoFactorCode, resp=Response('HTTP_401', 'HTTP_403', 'HTTP_409', HTTP_200=RecoveryCodes),
                   tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: TwoFactorCode) -> None:
        """Confirm the setup with the current code of the authenticator app (403 if wrong): from now on, the login needs
        a code. Answers the 10 recovery codes, shown only now. 409 without a setup started or once it is on."""
        with self._storage.transaction() as store:
            user_id = _user_id(req)
            state = store.users().two_factor(user_id)
            if state is None or state.enabled:
                raise ConflictError('Start the setup first' if state is None else 'Two-factor login is on already')
            if not code_accepted(store, user_id, json.code, self._clock(), enabled=False):
                raise falcon.HTTPForbidden(description='The code is wrong; enter the current one of your authenticator app')
            resp.media = RecoveryCodes(recovery_codes=_new_recovery_codes(store, user_id))
            record(store, self._clock(), user_id, 'two_factor_on', user_id)


def _setup(secret: str, username: str) -> TwoFactorSetup:
    """The secret for the authenticator app, as text and as QR code."""
    uri = provisioning_uri(secret, username)
    return TwoFactorSetup(secret=secret, uri=uri, qr=qr_code(uri))


def _new_recovery_codes(store: Store, user_id: str) -> list[str]:
    """New recovery codes for the user, replacing the old ones; only their hashes are kept."""
    users, codes = store.users(), new_recovery_codes()
    hashes = [recovery_hash(code) for code in codes]
    users.save_two_factor(user_id, users.two_factor(user_id).model_copy(update={'recovery': hashes}))
    return codes


class RecoveryCodesResource(_AuthResource):
    @spec.validate(json=TwoFactorOff, resp=Response('HTTP_401', 'HTTP_403', 'HTTP_409', HTTP_201=RecoveryCodes), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: TwoFactorOff) -> None:
        """New recovery codes, with the current password (403 if wrong); the old ones no longer work. 409 while
        two-factor login is off."""
        with self._storage.transaction() as store:
            users, user_id = store.users(), _user_id(req)
            if not users.check_password(user_id, json.password):
                raise falcon.HTTPForbidden(description='The current password is wrong')
            if not users.get(user_id).two_factor:
                raise ConflictError('Two-factor login is off')
            resp.media = RecoveryCodes(recovery_codes=_new_recovery_codes(store, user_id))
            record(store, self._clock(), user_id, 'recovery_codes_renewed', user_id)
        resp.status = falcon.HTTP_201


class NewAppResource(_AuthResource):
    @spec.validate(json=NewAppInput, resp=Response('HTTP_401', 'HTTP_403', 'HTTP_409', 'HTTP_429', HTTP_201=TwoFactorSetup),
                   tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: NewAppInput) -> None:
        """Start a new authenticator app (e.g. on a new phone), with the current password and a current code of the old
        app or a recovery code (403 if wrong; counts as a failed login, 429 after 5 within a minute): a new secret, as
        QR code and as text. The old app keeps working until a code of the new one confirms it (PUT); starting again
        replaces an unconfirmed new secret. 409 while two-factor login is off. Also for root and admins."""
        with self._storage.transaction() as store:
            setup, refusal = self._start(store, _user_id(req), json)
        if refusal:  # answered after the transaction, so the failed attempt is stored
            raise falcon.HTTPForbidden(description=refusal)
        resp.status = falcon.HTTP_201
        resp.media = setup

    def _start(self, store: Store, user_id: str, json: NewAppInput) -> tuple[TwoFactorSetup | None, str | None]:
        """The new secret, or why it was refused (counted as a failed login)."""
        now, attempts, users = self._clock(), store.attempts(), store.users()
        if attempts.paused(now):
            raise falcon.HTTPTooManyRequests(description=PAUSED)
        user = users.get(user_id)
        if not user.two_factor:
            raise ConflictError('Two-factor login is off')
        if not users.check_password(user_id, json.password):
            attempts.add(now)
            return None, 'The current password is wrong'
        if not code_or_recovery_accepted(store, user_id, json.code, now):
            attempts.add(now)
            return None, WRONG_CODE
        secret = new_secret()
        users.save_two_factor(user_id, users.two_factor(user_id).model_copy(update={'new_secret': secret}))
        return _setup(secret, user.username), None

    @spec.validate(json=TwoFactorCode, resp=Response('HTTP_204', 'HTTP_401', 'HTTP_403', 'HTTP_409'), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: TwoFactorCode) -> None:
        """Confirm the new authenticator app with its current code (403 if wrong): it replaces the old one, whose codes
        no longer work; the recovery codes stay. 409 without a new app started."""
        with self._storage.transaction() as store:
            user_id = _user_id(req)
            state = store.users().two_factor(user_id)
            if state is None or state.new_secret is None:
                raise ConflictError('Start with the password and a current code first')
            if not new_app_accepted(store, user_id, json.code, self._clock()):
                raise falcon.HTTPForbidden(description='The code is wrong; enter the current one of your new authenticator '
                                                       'app')
            record(store, self._clock(), user_id, 'two_factor_new_app', user_id)
        resp.status = falcon.HTTP_204


class TwoFactorOffResource(_AuthResource):
    @spec.validate(json=TwoFactorOff, resp=Response('HTTP_204', 'HTTP_401', 'HTTP_403'), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: TwoFactorOff) -> None:
        """Switch two-factor login off, with the current password (403 if wrong); not for root and admins (409), who
        must use it."""
        with self._storage.transaction() as store:
            users, user_id = store.users(), _user_id(req)
            if required(users.get(user_id)):
                raise ConflictError('Root and admins must use two-factor login')
            if not users.check_password(user_id, json.password):
                raise falcon.HTTPForbidden(description='The current password is wrong')
            users.save_two_factor(user_id, None)
            record(store, self._clock(), user_id, 'two_factor_off', user_id)
        resp.status = falcon.HTTP_204


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
            record(store, self._clock(), user_id, 'password_changed', user_id)
            self._log_in(req, resp, store, users.get(user_id))
        resp.status = falcon.HTTP_204
