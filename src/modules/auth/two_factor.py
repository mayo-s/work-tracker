"""Two-factor login (SPEC 5.6, TASKS.md 9.1g): the code of an authenticator app at login, and its setup with a QR
code."""

import datetime as dt

import falcon
import segno

from src.lib.totp import matching_step
from src.models.users import User
from src.modules.storage.store import Store

CODE_NEEDED = 'two_factor_required'  # the `code` of the 401 answer that asks for the authenticator code
WRONG_CODE = 'The code is wrong; enter the current one of your authenticator app'


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
    return code_accepted(store, user.id, code, now)
