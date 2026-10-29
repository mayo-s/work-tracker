"""Users who log in: username and e-mail address (both unique, ignoring case), name, and a password."""

from pydantic import Field

from src.models.base import DomainModel

USERNAME_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9._-]{2,29}$'
EMAIL_PATTERN = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
PASSWORD_MIN_LENGTH = 12


class User(DomainModel):
    id: int | None = None
    username: str = Field(pattern=USERNAME_PATTERN, description='3 to 30 letters, digits, dots, dashes or underscores')
    email: str = Field(pattern=EMAIL_PATTERN, max_length=200)
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(default='', max_length=50)
