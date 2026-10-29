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

Role = Literal['admin', 'team_admin', 'user']


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


def password_problem(password: str) -> str | None:
    """Why a new password is not allowed, or None: it needs at least 12 characters with letters, digits and a special
    character (anything but letters, digits and spaces). Existing passwords are not checked."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f'The password needs at least {PASSWORD_MIN_LENGTH} characters.'
    if not all(any(kind(char) for char in password) for kind in _PASSWORD_CHARACTERS):
        return 'The password needs letters, digits and a special character, e.g. ! ? # or %.'
    return None
