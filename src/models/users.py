"""Users who log in: username and e-mail address (both unique, ignoring case), name, and a password."""

import datetime as dt
from typing import Literal

from pydantic import Field

from src.models.base import DomainModel

USERNAME_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9._-]{2,29}$'
EMAIL_PATTERN = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
PASSWORD_MIN_LENGTH = 12

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
