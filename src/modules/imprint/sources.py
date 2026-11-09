"""Where the imprint's details are kept (SPEC 5.13), as JSON and never in the repository: on AWS Lambda an SSM
parameter, locally $WORK_TRACKER_IMPRINT. Both are read on each visit of the imprint, so a change shows at once."""

import os
from typing import Any

from botocore.exceptions import ClientError

VARIABLE = 'WORK_TRACKER_IMPRINT'


class EnvironmentImprint:
    """Locally: the details in $WORK_TRACKER_IMPRINT, e.g. from .env."""

    where = f'${VARIABLE}'

    def read(self) -> str | None:
        return os.environ.get(VARIABLE) or None


class ParameterImprint:
    """On AWS Lambda: the details in the SSM parameter with this name, a String or a SecureString."""

    def __init__(self, client: Any, parameter: str) -> None:
        self._client = client
        self._parameter = parameter
        self.where = f'the SSM parameter {parameter}'

    def read(self) -> str | None:
        try:
            return self._client.get_parameter(Name=self._parameter, WithDecryption=True)['Parameter']['Value']
        except ClientError as error:
            if error.response['Error']['Code'] != 'ParameterNotFound':
                raise
            return None


type ImprintSource = EnvironmentImprint | ParameterImprint
