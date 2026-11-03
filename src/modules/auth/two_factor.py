"""Two-factor login (SPEC 5.6, TASKS.md 9.1g): the code of an authenticator app at login, its setup with a QR code,
and recovery codes for a lost app. Root and admins must use it."""

import datetime as dt
import hashlib
import secrets

import falcon
import segno

from src.lib.totp import matching_step
from src.models.users import Role, User
from src.modules.storage.store import Store

CODE_NEEDED = 'two_factor_required'  # the `code` of the 401 answer that asks for the authenticator code
WRONG_CODE = 'The code is wrong; enter the current one of your authenticator app, or a recovery code'
REQUIRED: tuple[Role, ...] = ('root', 'admin')
RECOVERY_CODES = 10
_RECOVERY_LETTERS = 'abcdefghjkmnpqrstuvwxyz23456789'  # no 0/o, 1/l/i: easy to read off paper


def required(user: User) -> bool:
    """Root and admins must use two-factor login."""
    return user.role in REQUIRED


def new_recovery_codes() -> list[str]:
    """Ten codes like `k7qm3-xtp9w` (50 bits each), each replacing a code of the app once."""
    codes = [''.join(secrets.choice(_RECOVERY_LETTERS) for _ in range(10)) for _ in range(RECOVERY_CODES)]
    return [f'{code[:5]}-{code[5:]}' for code in codes]


def recovery_hash(code: str) -> str:
    """How a recovery code is kept: random enough that SHA-256 needs no salt; case, dashes and spaces do not matter."""
    return hashlib.sha256(code.lower().replace('-', '').replace(' ', '').encode()).hexdigest()


def qr_code(uri: str) -> str:
    """The QR code of the address as an SVG data URI, for an `<img>`."""
    return segno.make(uri, error='m').svg_data_uri(scale=5, border=2)


def code_accepted(store: Store, user_id: str, code: str, now: dt.datetime, enabled: bool = True) -> bool:
    """Whether the code fits the user's authenticator app (confirmed or, with `enabled` False, being set up); its time
    step is kept, so the same code is refused afterwards."""
    users = store.users()
    state = users.two_factor(user_id)
    if state is None or state.enabled != enabled:
        return False
    step = matching_step(state.secret, code, now, state.last_step)
    if step is None:
        return False
    users.save_two_factor(user_id, state.model_copy(update={'last_step': step, 'enabled': True}))
    return True


def second_factor(store: Store, user: User, code: str | None, now: dt.datetime) -> bool:
    """With two-factor login, the code is needed (401 with `code` two_factor_required without one); whether it fits.
    Without two-factor login, nothing is needed."""
    if not user.two_factor:
        return True
    if not code:
        raise falcon.HTTPUnauthorized(title='401 Unauthorized', code=CODE_NEEDED,
                                      description='Enter the code of your authenticator app')
    return code_accepted(store, user.id, code, now) or _recovery_accepted(store, user.id, code)


def _recovery_accepted(store: Store, user_id: str, code: str) -> bool:
    """Whether the code is one of the user's recovery codes not used yet; it is used up then."""
    users = store.users()
    state, hashed = users.two_factor(user_id), recovery_hash(code)
    if state is None or hashed not in state.recovery:
        return False
    users.save_two_factor(user_id, state.model_copy(update={'recovery': [kept for kept in state.recovery if kept != hashed]}))
    return True
