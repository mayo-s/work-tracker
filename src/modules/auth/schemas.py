"""Users, login and password as shown and entered in the API."""

from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from src.models.users import EMAIL_PATTERN, PASSWORD_MIN_LENGTH, PASSWORD_RULES, USERNAME_PATTERN, Role, User, password_problem
from src.modules.teams.schemas import TeamRef


def _allowed(password: str) -> str:
    if problem := password_problem(password):
        raise ValueError(problem)
    return password


NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=200, description=PASSWORD_RULES),
                        AfterValidator(_allowed)]


class UserView(BaseModel):
    id: str = Field(description='Random UUID')
    username: str
    email: str
    first_name: str
    last_name: str
    role: Role = Field(description='admin, team_admin or user')

    @classmethod
    def of(cls, user: User) -> Self:
        return cls(**user.model_dump())


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    username: str = Field(pattern=USERNAME_PATTERN, examples=['mario'],
                          description='3 to 30 letters, digits, dots, dashes or underscores')
    email: str = Field(pattern=EMAIL_PATTERN, max_length=200, examples=['mario@example.com'])
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(default='', max_length=50)

    def to_user(self, user_id: str | None = None) -> User:
        return User(id=user_id, **self.model_dump(include={'username', 'email', 'first_name', 'last_name'}))


class NewUserInput(ProfileInput):
    password: NewPassword


class LoginInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    login: str = Field(min_length=1, max_length=200, description='Username or e-mail address')
    password: str = Field(min_length=1, max_length=200)


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    current_password: str = Field(min_length=1, max_length=200)
    new_password: NewPassword


class AuthStatus(BaseModel):
    enabled: bool = Field(description='False when the login is switched off (WORK_TRACKER_AUTH=off)')
    has_users: bool = Field(description='False until the first user is created')
    user: UserView | None = Field(description='The logged-in user')
    registration: bool = Field(description='True while new users can register on /register')
    team: TeamRef | None = Field(default=None, description='The team of the logged-in user')
    invitations: int = Field(default=0, description='Open team invitations of the logged-in user')
