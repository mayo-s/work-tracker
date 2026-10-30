import pytest

from src.modules.storage.database import Database
from src.modules.storage.dynamodb.storage import DynamoStorage
from src.modules.storage.sqlite import SqliteStorage


@pytest.fixture(params=['sqlite', 'dynamodb'])
def storage(request, tmp_path):
    """Each backend in turn, migrated and empty: contract tests run on both."""
    if request.param == 'sqlite':
        backend = SqliteStorage(Database(tmp_path / 'contract.db'))
    else:
        backend = DynamoStorage(request.getfixturevalue('dynamo_table'))
    backend.migrate()
    return backend
