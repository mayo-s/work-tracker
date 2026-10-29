"""Users, their sessions and failed logins; works within the transaction of the given connection."""

import datetime as dt
import hashlib
import secrets
import sqlite3

from src.lib.passwords import hash_password, verify_password
from src.models.users import User
from src.modules.storage.errors import ConflictError, NotFoundError

SESSION_LIFETIME = dt.timedelta(hours=24)
SESSION_RENEWAL = dt.timedelta(minutes=30)  # the stored expiry is renewed at most this often
FAILED_LOGINS_ALLOWED = 5
FAILED_LOGIN_PAUSE = dt.timedelta(minutes=1)
_COLUMNS = 'id, username, email, first_name, last_name'


class UserRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def count(self) -> int:
        return self._conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]

    def get(self, user_id: int) -> User:
        row = self._conn.execute(f'SELECT {_COLUMNS} FROM users WHERE id = ?', (user_id,)).fetchone()
        if row is None:
            raise NotFoundError(f'No user with id {user_id}')
        return User(**dict(row))

    def add(self, user: User, password: str) -> User:
        sql = 'INSERT INTO users (username, email, first_name, last_name, password_hash) VALUES (?, ?, ?, ?, ?)'
        cursor = self._write(sql, (*_profile(user), hash_password(password)))
        return user.model_copy(update={'id': cursor.lastrowid})

    def update(self, user: User) -> User:
        sql = 'UPDATE users SET username = ?, email = ?, first_name = ?, last_name = ? WHERE id = ?'
        if not self._write(sql, (*_profile(user), user.id)).rowcount:
            raise NotFoundError(f'No user with id {user.id}')
        return user

    def by_login(self, login: str) -> User | None:
        """The user with this username or e-mail address (ignoring case)."""
        row = self._conn.execute(f'SELECT {_COLUMNS} FROM users WHERE username = ? OR email = ?',
                                 (login.strip(), login.strip())).fetchone()
        return User(**dict(row)) if row else None

    def check_password(self, user_id: int, password: str) -> bool:
        row = self._conn.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,)).fetchone()
        return row is not None and verify_password(password, row[0])

    def set_password(self, user_id: int, password: str) -> None:
        """A new password ends all sessions of the user."""
        self._conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (hash_password(password), user_id))
        self._conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))

    def _write(self, sql: str, params: tuple) -> sqlite3.Cursor:
        try:
            return self._conn.execute(sql, params)
        except sqlite3.IntegrityError as error:
            field = 'e-mail address' if 'email' in str(error) else 'username'
            raise ConflictError(f'This {field} is already taken') from error


class SessionRepository:
    """Sessions valid for 24 h since the last activity; the cookie holds the token, the table only its hash."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def start(self, user_id: int, now: dt.datetime) -> str:
        token = secrets.token_urlsafe(32)
        self._conn.execute('INSERT INTO sessions (token_hash, user_id, expires_at, renewed_at) VALUES (?, ?, ?, ?)',
                           (_hash(token), user_id, (now + SESSION_LIFETIME).isoformat(), now.isoformat()))
        return token

    def user_id(self, token: str, now: dt.datetime) -> tuple[int | None, bool]:
        """The user of a valid session and whether it was renewed now (the cookie then gets renewed too)."""
        row = self._conn.execute('SELECT user_id, expires_at, renewed_at FROM sessions WHERE token_hash = ?',
                                 (_hash(token),)).fetchone()
        if row is None or dt.datetime.fromisoformat(row['expires_at']) <= now:
            return None, False
        if now - dt.datetime.fromisoformat(row['renewed_at']) < SESSION_RENEWAL:
            return row['user_id'], False
        self._conn.execute('UPDATE sessions SET expires_at = ?, renewed_at = ? WHERE token_hash = ?',
                           ((now + SESSION_LIFETIME).isoformat(), now.isoformat(), _hash(token)))
        return row['user_id'], True

    def end(self, token: str) -> None:
        self._conn.execute('DELETE FROM sessions WHERE token_hash = ?', (_hash(token),))

    def end_expired(self, now: dt.datetime) -> None:
        self._conn.execute('DELETE FROM sessions WHERE expires_at <= ?', (now.isoformat(),))


class FailedLogins:
    """After 5 failed logins within a minute, logins pause until a minute after the last one."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def paused(self, now: dt.datetime) -> bool:
        since = (now - FAILED_LOGIN_PAUSE).isoformat()
        return self._conn.execute('SELECT COUNT(*) FROM failed_logins WHERE at > ?', (since,)).fetchone()[0] \
            >= FAILED_LOGINS_ALLOWED

    def add(self, now: dt.datetime) -> None:
        self._conn.execute('INSERT INTO failed_logins (at) VALUES (?)', (now.isoformat(),))
        self._conn.execute('DELETE FROM failed_logins WHERE at <= ?', ((now - FAILED_LOGIN_PAUSE).isoformat(),))

    def clear(self) -> None:
        self._conn.execute('DELETE FROM failed_logins')


def _profile(user: User) -> tuple:
    return user.username, user.email, user.first_name, user.last_name


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
