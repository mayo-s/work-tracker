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
    role: Role = Field(description='The app role: root (runs the app, tracks no work), admin or user (team roles: see team)')
    must_change_password: bool = Field(default=False, description='True after a one-time password, until the user chose '
                                                                  'their own')
    two_factor: bool = Field(default=False, description='Whether the login also needs a code of an authenticator app')

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


class RootInput(NewUserInput):
    setup_token: str | None = Field(default=None, description='Only on AWS Lambda: the setup token')


class RootResetInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    setup_token: str = Field(min_length=1, max_length=200, description='A new setup token (README, "Deploy to AWS")')
    new_password: NewPassword


class LoginInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    login: str = Field(min_length=1, max_length=200, description='Username or e-mail address')
    password: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=20,
                             description='With two-factor login: the code of the authenticator app')
    remember: bool = Field(default=False, description='With a code: this browser needs none for 30 days (not for root)')


class TwoFactorStatus(BaseModel):
    enabled: bool = Field(description='Whether the login also needs a code of an authenticator app')
    required: bool = Field(default=False, description='Root and admins must use it')
    recovery_left: int = Field(default=0, description='Recovery codes not used yet')


class RecoveryCodes(BaseModel):
    recovery_codes: list[str] = Field(description='Shown only now: each replaces a code of the app once, e.g. when the '
                                                  'phone is lost', examples=[['k7qm3-xtp9w']])


class TwoFactorSetup(BaseModel):
    secret: str = Field(description='For entering by hand, if the QR code cannot be scanned')
    uri: str = Field(description='The otpauth:// address the QR code holds')
    qr: str = Field(description='The QR code as an SVG data URI')


class TwoFactorCode(BaseModel):
    model_config = ConfigDict(extra='forbid')

    code: str = Field(min_length=6, max_length=20, description='The current code of the authenticator app')


class NewAppInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    password: str = Field(min_length=1, max_length=200, description='The current password')
    code: str = Field(min_length=6, max_length=20, description='The current code of the old authenticator app, or a '
                                                               'recovery code')


class TwoFactorOff(BaseModel):
    model_config = ConfigDict(extra='forbid')

    password: str = Field(min_length=1, max_length=200, description='The current password')


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    current_password: str = Field(min_length=1, max_length=200)
    new_password: NewPassword


class AuthStatus(BaseModel):
    enabled: bool = Field(description='False when the login is switched off (WORK_TRACKER_AUTH=off)')
    has_users: bool = Field(description='False until the first user is created')
    has_root: bool = Field(default=False, description='False until root, who runs the app, is created')
    user: UserView | None = Field(description='The logged-in user')
    registration: bool = Field(description='True while new users can register on /register')
    team: TeamRef | None = Field(default=None, description='The team of the logged-in user')
    invitations: int = Field(default=0, description='Open team invitations of the logged-in user')
    setup_token: bool = Field(default=False, description='True while creating root needs the setup token (AWS Lambda)')
    root_reset: bool = Field(default=False, description="True on AWS Lambda once root exists: root's login can be reset "
                                                        'with a new setup token')
