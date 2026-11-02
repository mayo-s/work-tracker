"""The stage the app runs in and the storage it uses there (SPEC 7.1): locally SQLite, on AWS Lambda DynamoDB.

Locally, STAGE=Local comes from .env, which pipenv loads; Lambda is recognized by AWS_LAMBDA_FUNCTION_NAME, which
Lambda sets itself. Anything else stops the app on start with a StageError saying what to change.
"""

import os
from enum import StrEnum

import boto3

from src.modules.auth.sessions import auth_enabled
from src.modules.auth.setup_token import SetupToken
from src.modules.storage.database import Database, database_path
from src.modules.storage.dynamodb.storage import DynamoStorage
from src.modules.storage.dynamodb.table import REGION, Table
from src.modules.storage.sqlite import SqliteStorage
from src.modules.storage.store import Storage

LOCAL_HINT = 'put STAGE=Local into .env to run locally; on AWS Lambda the stage is detected'


class Stage(StrEnum):
    LOCAL = 'LOCAL'
    LAMBDA = 'LAMBDA'


class StageError(RuntimeError):
    """The app cannot tell where it runs, or is configured wrongly for it."""


def current_stage() -> Stage:
    """Lambda when running on AWS Lambda, Local with STAGE=Local (in any case)."""
    stage = os.environ.get('STAGE', '')
    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
        if stage.lower() == 'local':
            raise StageError('STAGE=Local on AWS Lambda: remove it, the stage is detected there')
        return Stage.LAMBDA
    if not stage:
        raise StageError(f'STAGE is not set: {LOCAL_HINT}')
    if stage.lower() != 'local':
        raise StageError(f'Unknown STAGE={stage}: {LOCAL_HINT}')
    return Stage.LOCAL


def stage_storage() -> Storage:
    """The storage of the current stage: locally the SQLite file $WORK_TRACKER_DB (default work_tracker.db), on AWS
    Lambda the DynamoDB table named like the function (e.g. work-tracker-prod), or $WORK_TRACKER_TABLE."""
    if current_stage() is Stage.LOCAL:
        return SqliteStorage(Database(database_path()))
    if not auth_enabled():
        raise StageError('WORK_TRACKER_AUTH=off is for local development only, not on AWS Lambda')
    table = os.environ.get('WORK_TRACKER_TABLE') or os.environ['AWS_LAMBDA_FUNCTION_NAME']
    return DynamoStorage(Table(boto3.client('dynamodb', region_name=REGION), table))


def stage_setup_token() -> SetupToken | None:
    """The token creating root needs: on AWS Lambda from the SSM parameter named like the function (e.g.
    /work-tracker-prod/setup-token), or $WORK_TRACKER_SETUP_TOKEN_PARAMETER; locally none."""
    if current_stage() is Stage.LOCAL:
        return None
    function = os.environ['AWS_LAMBDA_FUNCTION_NAME']
    parameter = os.environ.get('WORK_TRACKER_SETUP_TOKEN_PARAMETER') or f'/{function}/setup-token'
    return SetupToken(boto3.client('ssm', region_name=REGION), parameter)
