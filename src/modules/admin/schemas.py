"""Users and app-wide settings as shown and entered on the admin page: accounts only, nothing of anyone's time data."""

import datetime as dt
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from src.models.users import Role, User


class AdminUserView(BaseModel):
    id: str = Field(description='Random UUID')
    username: str
    email: str
    first_name: str
    last_name: str
    role: Role
    active: bool = Field(description='False: deactivated, cannot log in')
    registered_at: dt.datetime | None = Field(description='Null for users registered before it was recorded')
    last_login_at: dt.datetime | None

    @classmethod
    def of(cls, user: User) -> Self:
        return cls(**user.model_dump())


class AdminUserInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    role: Literal['admin', 'user'] = Field(description='Team admins follow with teams (TASKS.md L.8a.3)')
    active: bool = Field(description='False deactivates the user: they cannot log in, their sessions end')


class AdminSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')

    registration: bool = Field(description='Whether new users can register on /register (off by default)')
