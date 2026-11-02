"""The setup token (SPEC 7.4): on AWS Lambda the URL is public, so only who knows it creates root, who runs the app.

It is a SecureString in the SSM Parameter Store, created by hand and never in the repository, and read only when root
is created or its login reset. Each token works once: the hashes of those used are kept. Locally there is none.
"""

import datetime as dt
import hashlib
import hmac
from collections.abc import Callable
from typing import Any

import falcon
from botocore.exceptions import ClientError

from src.modules.auth.sessions import PAUSED
from src.modules.storage.errors import ConflictError
from src.modules.storage.store import Storage

MIN_LENGTH = 32
DEFAULT_PARAMETER = '/work-tracker/setup-token'


class SetupToken:
    """The token in the parameter with this name."""

    def __init__(self, client: Any, parameter: str = DEFAULT_PARAMETER) -> None:
        self._client = client
        self._parameter = parameter

    def matches(self, given: str | None) -> bool:
        """Whether the given token is the stored one, compared in the same time for every token."""
        stored = self._stored()
        return given is not None and hmac.compare_digest(given.encode(), stored.encode())

    def _stored(self) -> str:
        try:
            value = self._client.get_parameter(Name=self._parameter, WithDecryption=True)['Parameter']['Value']
        except ClientError as error:
            if error.response['Error']['Code'] != 'ParameterNotFound':
                raise
            raise ConflictError(f'No setup token is configured: create the parameter {self._parameter} first') from error
        if len(value) < MIN_LENGTH:
            raise ConflictError(f'The setup token in {self._parameter} needs at least {MIN_LENGTH} characters')
        return value


def token_hash(token: str) -> str:
    """How a used token is kept: a long random token needs no salt or slow hash."""
    return hashlib.sha256(token.encode()).hexdigest()


def check_setup_token(
    storage: Storage, setup_token: SetupToken | None, given: str | None, clock: Callable[[], dt.datetime],
) -> str | None:
    """Before creating root or resetting its login: with a setup token (AWS Lambda), it must be given. Returns its hash
    for `use_setup_token` in the transaction of the change, which refuses a token used before (409); None without a
    setup token.

    A wrong token counts as a failed login, kept in a transaction of its own: trying pauses after 5 within a minute
    (429).
    """
    if setup_token is None:
        return None
    with storage.transaction() as store:
        attempts, now = store.attempts(), clock()
        if attempts.paused(now):
            raise falcon.HTTPTooManyRequests(description=PAUSED)
        wrong = not setup_token.matches(given)
        if wrong:
            attempts.add(now)
    if wrong:
        raise falcon.HTTPForbidden(description='The setup token is wrong')
    return token_hash(given or '')
