"""Users, their sessions and login attempts; works within the transaction of the given connection."""

import datetime as dt
import hashlib
import json
import secrets
import sqlite3
import uuid
from collections.abc import Callable

from src.lib.passwords import hash_password, verify_password
from src.models.users import Role, TwoFactor, User
from src.modules.storage.errors import TAKEN, ConflictError, NotFoundError
from src.modules.storage.owners import start_with_defaults, take_over_unowned

SESSION_LIFETIME = dt.timedelta(hours=24)
SESSION_RENEWAL = dt.timedelta(minutes=30)  # the stored expiry is renewed at most this often
ROOT_SESSION_LIFETIME = dt.timedelta(hours=1)  # root, the strongest account: a forgotten tab soon ends
ROOT_SESSION_RENEWAL = dt.timedelta(minutes=5)
BROWSER_LIFETIME = dt.timedelta(days=30)  # a remembered browser skips the code of two-factor login
ATTEMPTS_ALLOWED = 5  # failed logins and registrations together
ATTEMPT_PAUSE = dt.timedelta(minutes=1)
_COLUMNS = ('id, username, email, first_name, last_name, role, active, registered_at, last_login_at, must_change_password,'
            ' two_factor, support')


def session_lifetime(role: str) -> dt.timedelta:
    """How long a session lasts since the last activity: 24 hours, root's 1 hour."""
    return ROOT_SESSION_LIFETIME if role == 'root' else SESSION_LIFETIME


def session_renewal(role: str) -> dt.timedelta:
    return ROOT_SESSION_RENEWAL if role == 'root' else SESSION_RENEWAL


def random_id() -> str:
    return str(uuid.uuid4())


class UserRepository:
    def __init__(
        self, conn: sqlite3.Connection, clock: Callable[[], dt.datetime] | None = None, new_id: Callable[[], str] = random_id,
    ) -> None:
        self._conn = conn
        self._clock = clock or dt.datetime.now
        self._new_id = new_id

    def count(self) -> int:
        return self._conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]

    def get(self, user_id: str) -> User:
        row = self._conn.execute(f'SELECT {_COLUMNS} FROM users WHERE id = ?', (user_id,)).fetchone()
        if row is None:
            raise NotFoundError(f'No user with id {user_id}')
        return User(**dict(row))

    def add(self, user: User, password: str) -> User:
        """A new user with their role: root (only one, 409 for a second) tracks no work; anyone else starts with the
        default activity types and the setup still to do, and the first of them takes over all records without an
        owner."""
        root = user.role == 'root'
        if root and self.root_id():
            raise ConflictError('There is a root already')
        first = not root and self.first_id() is None
        added = user.model_copy(update={'id': self._new_id(), 'active': True, 'registered_at': self._clock()})
        sql = 'INSERT INTO users (id, username, email, first_name, last_name, role, registered_at, password_hash)' \
              ' VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
        self._write(sql, (added.id, *_profile(added), added.role, added.registered_at.isoformat(), hash_password(password)))
        if first:
            take_over_unowned(self._conn, added.id)
        if not root:
            start_with_defaults(self._conn, added.id)
        return added

    def all(self) -> list[User]:
        """All users in the order they registered."""
        return [User(**dict(row)) for row in self._conn.execute(f'SELECT {_COLUMNS} FROM users ORDER BY rowid')]

    def set_role(self, user_id: str, role: Role) -> User:
        self._conn.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))
        return self.get(user_id)

    def set_active(self, user_id: str, active: bool) -> User:
        """A deactivated user cannot log in, and their sessions end at once; their data is kept."""
        self._conn.execute('UPDATE users SET active = ? WHERE id = ?', (int(active), user_id))
        if not active:
            self._conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
        return self.get(user_id)

    def set_support(self, user_id: str, support: bool) -> User:
        """Whether the user answers the messages of the contact page (SPEC 5.14)."""
        self._conn.execute('UPDATE users SET support = ? WHERE id = ?', (int(support), user_id))
        return self.get(user_id)

    def first_id(self) -> str | None:
        """The first user who is not root, as whom the app acts when the login is off (the rowid keeps the order of
        creation)."""
        row = self._conn.execute("SELECT id FROM users WHERE role != 'root' ORDER BY rowid LIMIT 1").fetchone()
        return row[0] if row else None

    def root_id(self) -> str | None:
        row = self._conn.execute("SELECT id FROM users WHERE role = 'root'").fetchone()
        return row[0] if row else None

    def update(self, user: User) -> User:
        sql = 'UPDATE users SET username = ?, email = ?, first_name = ?, last_name = ? WHERE id = ?'
        if not self._write(sql, (*_profile(user), user.id)).rowcount:
            raise NotFoundError(f'No user with id {user.id}')
        return self.get(user.id)  # the role stays as it is

    def by_login(self, login: str) -> User | None:
        """The user with this username or e-mail address (ignoring case)."""
        row = self._conn.execute(f'SELECT {_COLUMNS} FROM users WHERE username = ? OR email = ?',
                                 (login.strip(), login.strip())).fetchone()
        return User(**dict(row)) if row else None

    def check_password(self, user_id: str, password: str) -> bool:
        row = self._conn.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,)).fetchone()
        return row is not None and verify_password(password, row[0])

    def password_hash(self, user_id: str) -> str:
        """The stored hash, for the full backup only."""
        self.get(user_id)
        return self._conn.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,)).fetchone()[0]

    def restore(self, user: User, password_hash: str) -> None:
        """A user of the full backup as they were (id, role, status, times, password); no defaults, no take-over."""
        sql = 'INSERT INTO users (id, username, email, first_name, last_name, role, active, registered_at, last_login_at,' \
              ' must_change_password, support, password_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        self._write(sql, (user.id, *_profile(user), user.role, int(user.active), _iso(user.registered_at),
                          _iso(user.last_login_at), int(user.must_change_password), int(user.support), password_hash))

    def set_password(self, user_id: str, password: str) -> None:
        """A new password ends all sessions of the user."""
        self._set_password(user_id, password, must_change=False)

    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        """A password as its hash (root taking over the login of a full backup's root); ends all sessions of the user."""
        self._conn.execute('UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?',
                           (password_hash, user_id))
        self._conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))

    def set_one_time_password(self, user_id: str, password: str) -> None:
        """A password from an admin: it ends all sessions, and the user chooses their own at the next login."""
        self.get(user_id)
        self._set_password(user_id, password, must_change=True)

    def two_factor(self, user_id: str) -> TwoFactor | None:
        row = self._conn.execute('SELECT two_factor_secret, two_factor, two_factor_step, two_factor_recovery,'
                                 ' two_factor_new_secret FROM users WHERE id = ?', (user_id,)).fetchone()
        if row is None or row[0] is None:
            return None
        return TwoFactor(secret=row[0], enabled=bool(row[1]), last_step=row[2], recovery=json.loads(row[3]),
                         new_secret=row[4])

    def save_two_factor(self, user_id: str, state: TwoFactor | None) -> None:
        """The authenticator app being set up, confirmed, with a code used or a new app; None switches two-factor
        login off and forgets the remembered browsers."""
        values = (state.secret, int(state.enabled), state.last_step, json.dumps(state.recovery), state.new_secret) if state \
            else (None, 0, 0, '[]', None)
        self._conn.execute('UPDATE users SET two_factor_secret = ?, two_factor = ?, two_factor_step = ?,'
                           ' two_factor_recovery = ?, two_factor_new_secret = ? WHERE id = ?', (*values, user_id))
        if state is None:
            BrowserRepository(self._conn).forget(user_id)

    def _set_password(self, user_id: str, password: str, must_change: bool) -> None:
        self._conn.execute('UPDATE users SET password_hash = ?, must_change_password = ? WHERE id = ?',
                           (hash_password(password), int(must_change), user_id))
        self._conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
        BrowserRepository(self._conn).forget(user_id)

    def _write(self, sql: str, params: tuple) -> sqlite3.Cursor:
        try:
            return self._conn.execute(sql, params)
        except sqlite3.IntegrityError as error:
            raise ConflictError(TAKEN['email' if 'email' in str(error) else 'username']) from error


class SessionRepository:
    """Sessions valid for 24 h since the last activity (root's for 1 h); the cookie holds the token, the table only its
    hash."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def start(self, user_id: str, now: dt.datetime) -> str:
        """A new session (at a login, a registration or a password change), recorded as the user's last login."""
        token = secrets.token_urlsafe(32)
        role = self._conn.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()[0]
        self._conn.execute('INSERT INTO sessions (token_hash, user_id, expires_at, renewed_at) VALUES (?, ?, ?, ?)',
                           (token_hash(token), user_id, (now + session_lifetime(role)).isoformat(), now.isoformat()))
        self._conn.execute('UPDATE users SET last_login_at = ? WHERE id = ?', (now.isoformat(), user_id))
        return token

    def user_id(self, token: str, now: dt.datetime) -> tuple[str | None, bool]:
        """The user of a valid session and whether it was renewed now (the cookie then gets renewed too)."""
        row = self._conn.execute('SELECT user_id, role, expires_at, renewed_at FROM sessions JOIN users ON users.id = user_id'
                                 ' WHERE token_hash = ? AND active', (token_hash(token),)).fetchone()
        if row is None or dt.datetime.fromisoformat(row['expires_at']) <= now:
            return None, False
        if now - dt.datetime.fromisoformat(row['renewed_at']) < session_renewal(row['role']):
            return row['user_id'], False
        self._conn.execute('UPDATE sessions SET expires_at = ?, renewed_at = ? WHERE token_hash = ?',
                           ((now + session_lifetime(row['role'])).isoformat(), now.isoformat(), token_hash(token)))
        return row['user_id'], True

    def end(self, token: str) -> None:
        self._conn.execute('DELETE FROM sessions WHERE token_hash = ?', (token_hash(token),))

    def end_expired(self, now: dt.datetime) -> None:
        self._conn.execute('DELETE FROM sessions WHERE expires_at <= ?', (now.isoformat(),))


class BrowserRepository:
    """Browsers that skip the code of two-factor login for 30 days ("Remember this browser"); their cookie holds the
    token, the table only its hash. A new password or switching two-factor login off forgets them."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def remember(self, user_id: str, now: dt.datetime) -> str:
        token = secrets.token_urlsafe(32)
        self._conn.execute('DELETE FROM remembered_browsers WHERE expires_at <= ?', (now.isoformat(),))
        self._conn.execute('INSERT INTO remembered_browsers (token_hash, user_id, expires_at) VALUES (?, ?, ?)',
                           (token_hash(token), user_id, (now + BROWSER_LIFETIME).isoformat()))
        return token

    def known(self, user_id: str, token: str, now: dt.datetime) -> bool:
        """Whether the browser with this token is remembered for the user, and not expired."""
        return self._conn.execute('SELECT 1 FROM remembered_browsers WHERE token_hash = ? AND user_id = ? AND expires_at > ?',
                                  (token_hash(token), user_id, now.isoformat())).fetchone() is not None

    def forget(self, user_id: str) -> None:
        self._conn.execute('DELETE FROM remembered_browsers WHERE user_id = ?', (user_id,))


class LoginAttempts:
    """Failed logins and registrations: after 5 within a minute, both pause until a minute after the last one."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def paused(self, now: dt.datetime) -> bool:
        since = (now - ATTEMPT_PAUSE).isoformat()
        return self._conn.execute('SELECT COUNT(*) FROM login_attempts WHERE at > ?', (since,)).fetchone()[0] \
            >= ATTEMPTS_ALLOWED

    def add(self, now: dt.datetime, kind: str = 'failed_login') -> None:
        """Record a failed login or a registration (`kind`), and forget the attempts older than the pause."""
        self._conn.execute('INSERT INTO login_attempts (at, kind) VALUES (?, ?)', (now.isoformat(), kind))
        self._conn.execute('DELETE FROM login_attempts WHERE at <= ?', ((now - ATTEMPT_PAUSE).isoformat(),))

    def clear_failed(self, now: dt.datetime) -> None:
        """After a successful login, the failed logins up to now no longer count; registrations still do."""
        self._conn.execute("DELETE FROM login_attempts WHERE kind = 'failed_login' AND at <= ?", (now.isoformat(),))


def _profile(user: User) -> tuple:
    return user.username, user.email, user.first_name, user.last_name


def _iso(moment: dt.datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def token_hash(token: str) -> str:
    """How a session token is stored: its SHA-256, never the token itself."""
    return hashlib.sha256(token.encode()).hexdigest()
