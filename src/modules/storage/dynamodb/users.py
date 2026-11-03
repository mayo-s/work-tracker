"""Users, their sessions and login attempts on DynamoDB, with the same rules as the SQLite repositories (users.py)."""

import datetime as dt
import secrets
from collections.abc import Callable

from src.lib.passwords import hash_password, verify_password
from src.models.base import new_id as new_record_id
from src.models.users import Role, TwoFactor, User
from src.modules.storage.dynamodb.catalog import add_default_activity_types
from src.modules.storage.dynamodb.keys import ATTEMPTS, LOGIN, ROOT, USERS, user_partition
from src.modules.storage.dynamodb.table import Item
from src.modules.storage.dynamodb.unit import Unit
from src.modules.storage.errors import NotFoundError
from src.modules.storage.users import (
    ATTEMPT_PAUSE, ATTEMPTS_ALLOWED, BROWSER_LIFETIME, random_id, session_lifetime, session_renewal, token_hash,
)

_PROFILE = ('username', 'email', 'first_name', 'last_name')
_TAKEN = {'username': 'This username is already taken', 'email': 'This e-mail address is already taken'}
_LAST = '\U0010ffff'  # sorts after every other character, as the end of a sort key range


def _profile_key(user_id: str) -> str:
    return f'USER#{user_id}'


def _login_key(field: str, value: str) -> str:
    return f'{"USERNAME" if field == "username" else "EMAIL"}#{value.strip().lower()}'


def _user(item: Item) -> User:
    return User(id=item['id'], **{field: item[field] for field in _PROFILE}, role=item['role'], active=item['active'],
                registered_at=item.get('registered_at'), last_login_at=item.get('last_login_at'),
                must_change_password=item.get('must_change_password', False),
                two_factor=bool(item.get('two_factor_secret')) and item.get('two_factor_on', False))


def _epoch(moment: dt.datetime) -> int:
    """Seconds since 1970 for DynamoDB's time to live (deleted some time after)."""
    return int(moment.timestamp()) + 1


class DynamoUsers:
    """App-wide user profiles in the `USERS` partition; usernames and e-mail addresses are kept unique (ignoring case)
    by `LOGIN` items, which also find a user by either."""

    def __init__(self, unit: Unit, clock: Callable[[], dt.datetime] | None = None,
                 new_id: Callable[[], str] = random_id) -> None:
        self._unit = unit
        self._clock = clock or dt.datetime.now
        self._new_id = new_id

    def count(self) -> int:
        return len(self._profiles())

    def get(self, user_id: str) -> User:
        return _user(self._profile(user_id))

    def add(self, user: User, password: str) -> User:
        """A new user with their role: root (only one, kept unique by `USERS` / `ROOT`) tracks no work; anyone else
        starts with the default activity types and the setup still to do."""
        added = user.model_copy(update={'id': self._new_id(), 'active': True, 'registered_at': self._clock()})
        if added.role == 'root':
            self._unit.put({'PK': USERS, 'SK': ROOT, 'user_id': added.id}, unique='There is a root already')
        for field in ('username', 'email'):
            self._claim(field, getattr(added, field), added.id)
        self._unit.put({'PK': USERS, 'SK': _profile_key(added.id), 'order': new_record_id(),
                        'password_hash': hash_password(password)} | _values(added))
        if added.role != 'root':
            add_default_activity_types(self._unit, added.id)
        return added

    def all(self) -> list[User]:
        """All users in the order they registered."""
        return [_user(item) for item in self._profiles()]

    def set_role(self, user_id: str, role: Role) -> User:
        self._change(user_id, role=role)
        return self.get(user_id)

    def set_active(self, user_id: str, active: bool) -> User:
        """A deactivated user cannot log in, and their sessions end at once; their data is kept."""
        self._change(user_id, active=active)
        if not active:
            end_sessions(self._unit, user_id)
        return self.get(user_id)

    def first_id(self) -> str | None:
        """The first user who is not root, as whom the app acts when the login is off."""
        return next((item['id'] for item in self._profiles() if item['role'] != 'root'), None)

    def root_id(self) -> str | None:
        item = self._unit.get(USERS, ROOT)
        return item['user_id'] if item else None

    def update(self, user: User) -> User:
        """The profile (username, e-mail address, name); the role stays as it is."""
        stored = self._profile(user.id)
        for field in ('username', 'email'):
            if _login_key(field, stored[field]) != _login_key(field, getattr(user, field)):
                self._claim(field, getattr(user, field), user.id)
                self._unit.delete(LOGIN, _login_key(field, stored[field]))
        self._unit.put(stored | {field: getattr(user, field) for field in _PROFILE})
        return self.get(user.id)

    def by_login(self, login: str) -> User | None:
        """The user with this username or e-mail address (ignoring case)."""
        for field in ('username', 'email'):
            if found := self._unit.get(LOGIN, _login_key(field, login)):
                return self.get(found['user_id'])
        return None

    def check_password(self, user_id: str, password: str) -> bool:
        item = self._unit.get(USERS, _profile_key(user_id))
        return item is not None and verify_password(password, item['password_hash'])

    def password_hash(self, user_id: str) -> str:
        """The stored hash, for the full backup only."""
        return self._profile(user_id)['password_hash']

    def restore(self, user: User, password_hash: str) -> None:
        """A user of the full backup as they were (id, role, status, times, password); no defaults."""
        if user.role == 'root':
            self._unit.put({'PK': USERS, 'SK': ROOT, 'user_id': user.id}, unique='There is a root already')
        for field in ('username', 'email'):
            self._claim(field, getattr(user, field), user.id)
        self._unit.put({'PK': USERS, 'SK': _profile_key(user.id), 'order': new_record_id(), 'password_hash': password_hash}
                       | _values(user) | {'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
                                          'must_change_password': user.must_change_password})

    def set_password(self, user_id: str, password: str) -> None:
        """A new password ends all sessions of the user."""
        self._change(user_id, password_hash=hash_password(password), must_change_password=False)
        end_sessions(self._unit, user_id)
        DynamoBrowsers(self._unit).forget(user_id)

    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        """A password as its hash (root taking over the login of a full backup's root); ends all sessions of the user."""
        self._change(user_id, password_hash=password_hash, must_change_password=False)
        end_sessions(self._unit, user_id)

    def set_one_time_password(self, user_id: str, password: str) -> None:
        """A password from an admin: it ends all sessions, and the user chooses their own at the next login."""
        self._change(user_id, password_hash=hash_password(password), must_change_password=True)
        end_sessions(self._unit, user_id)
        DynamoBrowsers(self._unit).forget(user_id)

    def two_factor(self, user_id: str) -> TwoFactor | None:
        item = self._profile(user_id)
        if not item.get('two_factor_secret'):
            return None
        return TwoFactor(secret=item['two_factor_secret'], enabled=item['two_factor_on'], last_step=item['two_factor_step'],
                         recovery=item.get('two_factor_recovery', []), new_secret=item.get('two_factor_new_secret'))

    def save_two_factor(self, user_id: str, state: TwoFactor | None) -> None:
        """The authenticator app being set up, confirmed, with a code used or a new app; None switches two-factor
        login off and forgets the remembered browsers."""
        self._change(user_id, **_two_factor_values(state))
        if state is None:
            DynamoBrowsers(self._unit).forget(user_id)

    def _profiles(self) -> list[Item]:
        return sorted(self._unit.query_prefix(USERS, 'USER#'), key=lambda item: item['order'])

    def _profile(self, user_id: str) -> Item:
        item = self._unit.get(USERS, _profile_key(user_id))
        if item is None:
            raise NotFoundError(f'No user with id {user_id}')
        return item

    def _change(self, user_id: str, **values: object) -> None:
        self._unit.put(self._profile(user_id) | values)

    def _claim(self, field: str, value: str, user_id: str) -> None:
        self._unit.put({'PK': LOGIN, 'SK': _login_key(field, value), 'user_id': user_id}, unique=_TAKEN[field])


def _values(user: User) -> Item:
    return {'id': user.id, **{field: getattr(user, field) for field in _PROFILE}, 'role': user.role, 'active': user.active,
            'registered_at': user.registered_at.isoformat() if user.registered_at else None, 'last_login_at': None}


def _two_factor_values(state: TwoFactor | None) -> Item:
    if state is None:
        return {'two_factor_secret': None, 'two_factor_on': False, 'two_factor_step': 0, 'two_factor_recovery': [],
                'two_factor_new_secret': None}
    return {'two_factor_secret': state.secret, 'two_factor_on': state.enabled, 'two_factor_step': state.last_step,
            'two_factor_recovery': state.recovery, 'two_factor_new_secret': state.new_secret}


def end_sessions(unit: Unit, user_id: str) -> None:
    """End all sessions of a user (each has an item in the user's partition pointing to it)."""
    for reference in unit.query_prefix(user_partition(user_id), 'SESSION#'):
        unit.delete(reference['SK'], 'SESSION')
        unit.delete(reference['PK'], reference['SK'])


class DynamoSessions:
    """Sessions valid for 24 h since the last activity (root's for 1 h); the cookie holds the token, the table only its
    hash."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit

    def start(self, user_id: str, now: dt.datetime) -> str:
        """A new session (at a login, a registration or a password change), recorded as the user's last login."""
        token = secrets.token_urlsafe(32)
        self._save(token_hash(token), user_id, now)
        if profile := self._unit.get(USERS, _profile_key(user_id)):
            self._unit.put(profile | {'last_login_at': now.isoformat()})
        return token

    def user_id(self, token: str, now: dt.datetime) -> tuple[str | None, bool]:
        """The user of a valid session and whether it was renewed now (the cookie then gets renewed too)."""
        session = self._unit.get(f'SESSION#{token_hash(token)}', 'SESSION')
        profile = self._active_profile(session, now)
        if profile is None:
            return None, False
        if now - dt.datetime.fromisoformat(session['renewed_at']) < session_renewal(profile['role']):
            return session['user_id'], False
        self._save(token_hash(token), session['user_id'], now)
        return session['user_id'], True

    def end(self, token: str) -> None:
        if session := self._unit.get(f'SESSION#{token_hash(token)}', 'SESSION'):
            self._unit.delete(session['PK'], 'SESSION')
            self._unit.delete(user_partition(session['user_id']), session['PK'])

    def end_expired(self, now: dt.datetime) -> None:
        """Nothing to do: time to live deletes expired sessions, and `user_id` refuses them until then."""

    def _active_profile(self, session: Item | None, now: dt.datetime) -> Item | None:
        """The profile of the session's user if the session is valid and the user active."""
        if session is None or dt.datetime.fromisoformat(session['valid_until']) <= now:
            return None
        profile = self._unit.get(USERS, _profile_key(session['user_id']))
        return profile if profile and profile['active'] else None

    def _save(self, hashed: str, user_id: str, now: dt.datetime) -> None:
        profile = self._unit.get(USERS, _profile_key(user_id))
        valid_until = now + session_lifetime(profile['role'] if profile else 'user')
        expiry = {'valid_until': valid_until.isoformat(), 'expires_at': _epoch(valid_until)}
        self._unit.put({'PK': f'SESSION#{hashed}', 'SK': 'SESSION', 'user_id': user_id,
                        'renewed_at': now.isoformat()} | expiry)
        self._unit.put({'PK': user_partition(user_id), 'SK': f'SESSION#{hashed}'} | expiry)


class DynamoBrowsers:
    """Browsers that skip the code of two-factor login for 30 days, in the user's partition (`BROWSER#<hash>`, time to
    live); their cookie holds the token. A new password or switching two-factor login off forgets them."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit

    def remember(self, user_id: str, now: dt.datetime) -> str:
        token = secrets.token_urlsafe(32)
        valid_until = now + BROWSER_LIFETIME
        self._unit.put({'PK': user_partition(user_id), 'SK': f'BROWSER#{token_hash(token)}',
                        'valid_until': valid_until.isoformat(), 'expires_at': _epoch(valid_until)})
        return token

    def known(self, user_id: str, token: str, now: dt.datetime) -> bool:
        item = self._unit.get(user_partition(user_id), f'BROWSER#{token_hash(token)}')
        return item is not None and dt.datetime.fromisoformat(item['valid_until']) > now

    def forget(self, user_id: str) -> None:
        for item in self._unit.query_prefix(user_partition(user_id), 'BROWSER#'):
            self._unit.delete(item['PK'], item['SK'])


class DynamoAttempts:
    """Failed logins and registrations: after 5 within a minute, both pause until a minute after the last one."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit

    def paused(self, now: dt.datetime) -> bool:
        cleared = (self._unit.get(ATTEMPTS, 'CLEARED') or {}).get('at', '')
        recent = self._unit.query(ATTEMPTS, f'AT#{_moment(now - ATTEMPT_PAUSE)}#{_LAST}', f'AT#{_LAST}')
        return sum(attempt['kind'] != 'failed_login' or attempt['at'] > cleared for attempt in recent) >= ATTEMPTS_ALLOWED

    def add(self, now: dt.datetime, kind: str = 'failed_login') -> None:
        """Record a failed login or a registration (`kind`); time to live deletes it after the pause."""
        self._unit.put({'PK': ATTEMPTS, 'SK': f'AT#{_moment(now)}#{secrets.token_hex(4)}', 'at': _moment(now), 'kind': kind,
                        'expires_at': _epoch(now + ATTEMPT_PAUSE)})

    def clear_failed(self, now: dt.datetime) -> None:
        """After a successful login, the failed logins up to now no longer count; registrations still do."""
        self._unit.put({'PK': ATTEMPTS, 'SK': 'CLEARED', 'at': _moment(now)})


def _moment(moment: dt.datetime) -> str:
    """A time that sorts as text in time order (always with microseconds)."""
    return moment.strftime('%Y-%m-%dT%H:%M:%S.%f')
