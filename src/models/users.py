"""Users who log in: username and e-mail address (both unique, ignoring case), name, and a password (rules for new ones)."""

import datetime as dt
from typing import Literal

from pydantic import Field

from src.models.base import DomainModel

USERNAME_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9._-]{2,29}$'
EMAIL_PATTERN = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
PASSWORD_MIN_LENGTH = 12
PASSWORD_RULES = f'At least {PASSWORD_MIN_LENGTH} characters with letters, digits and a special character'
# a letter, a digit and a special character (anything but letters, digits and spaces)
_PASSWORD_CHARACTERS = (str.isalpha, str.isdecimal, lambda char: not char.isalnum() and not char.isspace())

# The app role (a team admin is a member's team role, teams.py): exactly one root runs the app and tracks no work
Role = Literal['root', 'admin', 'user']
AssignableRole = Literal['admin', 'user']  # root is created once, never given or taken


class User(DomainModel):
    id: str | None = None  # a random UUID
    username: str = Field(pattern=USERNAME_PATTERN, description='3 to 30 letters, digits, dots, dashes or underscores')
    email: str = Field(pattern=EMAIL_PATTERN, max_length=200)
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(default='', max_length=50)
    role: Role = 'user'
    active: bool = True  # a deactivated user cannot log in
    registered_at: dt.datetime | None = None  # None: registered before it was recorded
    last_login_at: dt.datetime | None = None
    must_change_password: bool = False  # after a one-time password from an admin, until the user chose their own
    two_factor: bool = False  # the login also needs a code of their authenticator app
    support: bool = False  # answers the messages of the contact page (SPEC 5.14); never root

    @property
    def full_name(self) -> str:
        return ' '.join(filter(None, (self.first_name, self.last_name)))


class TwoFactor(DomainModel):
    """A user's authenticator app (TOTP): its secret, whether it is confirmed, and the last time step used (a code
    works only once); a new app (e.g. on a new phone) until a code of it confirms it. Never shown again after the setup,
    and not part of `User`."""

    secret: str
    enabled: bool = False  # False while being set up: a first code confirms it
    last_step: int = 0
    recovery: list[str] = []  # SHA-256 hashes of the recovery codes not used yet
    new_secret: str | None = None  # a new authenticator app: replaces `secret` once a code of it confirms it


def password_problem(password: str) -> str | None:
    """Why a new password is not allowed, or None: it needs at least 12 characters with letters, digits and a special
    character (anything but letters, digits and spaces). Existing passwords are not checked."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f'The password needs at least {PASSWORD_MIN_LENGTH} characters.'
    if not all(any(kind(char) for char in password) for kind in _PASSWORD_CHARACTERS):
        return 'The password needs letters, digits and a special character, e.g. ! ? # or %.'
    return None
