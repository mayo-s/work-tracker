"""Only through the domain (SPEC 7.4): on AWS Lambda, CloudFront adds a secret header to every request it passes on to
the Function URL, and the app refuses requests without it, so nobody bypasses the domain.

The secret is a SecureString in the SSM Parameter Store, created by hand and never in the repository, and read once per
Lambda instance. Locally there is none, and no check.
"""

import hmac
import logging
from typing import Any

import falcon
from botocore.exceptions import ClientError

from src.lib.texts import text

HEADER = 'X-Origin-Verify'
DEFAULT_PARAMETER = '/work-tracker/origin-secret'
REFUSED = text('Open the app at its address')

logger = logging.getLogger(__name__)


class OriginSecret:
    """The secret in the parameter with this name."""

    def __init__(self, client: Any, parameter: str = DEFAULT_PARAMETER) -> None:
        self._client = client
        self._parameter = parameter
        self._value: str | None = None

    def matches(self, given: str | None) -> bool:
        """Whether the given secret is the stored one, compared in the same time for every secret; never without a
        stored one."""
        stored = self._stored()
        return stored is not None and given is not None and hmac.compare_digest(given.encode(), stored.encode())

    def _stored(self) -> str | None:
        """Read once; until the parameter exists, every request asks again (and is refused)."""
        if self._value is None:
            try:
                self._value = self._client.get_parameter(Name=self._parameter, WithDecryption=True)['Parameter']['Value']
            except ClientError as error:
                if error.response['Error']['Code'] != 'ParameterNotFound':
                    raise
                logger.warning('No origin secret: create the parameter %s, so CloudFront reaches the app', self._parameter)
        return self._value


class OriginCheck:
    """Middleware: refuses (403) every request without the secret header, before anything else."""

    def __init__(self, secret: OriginSecret) -> None:
        self._secret = secret

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        if not self._secret.matches(req.get_header(HEADER)):
            raise falcon.HTTPForbidden(description=REFUSED)
