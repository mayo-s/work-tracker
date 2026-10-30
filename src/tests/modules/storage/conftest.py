import pytest

from src.modules.storage.database import Database
from src.modules.storage.dynamodb.storage import DynamoStorage
from src.modules.storage.sqlite import SqliteStorage
from src.tests.users import KLARA


@pytest.fixture(params=['sqlite', 'dynamodb'])
def storage(request, tmp_path):
    """Each backend in turn, migrated and empty: contract tests run on both."""
    if request.param == 'sqlite':
        backend = SqliteStorage(Database(tmp_path / 'contract.db'))
    else:
        backend = DynamoStorage(request.getfixturevalue('dynamo_table'))
    backend.migrate()
    return backend


@pytest.fixture
def klara_id(storage):
    """Klara as the first user, with the default activity types (ids 1 to 4 on both backends)."""
    with storage.transaction() as store:
        return store.users().add(KLARA, 'correct horse battery 9!').id


class PerCall:
    """A repository whose every call runs in a transaction of its own, so a test sees what was stored, not only what
    one transaction holds."""

    def __init__(self, storage, repository):
        self._storage = storage
        self._repository = repository

    def __getattr__(self, name):
        def call(*args, **kwargs):
            with self._storage.transaction() as store:
                return getattr(self._repository(store), name)(*args, **kwargs)
        return call


@pytest.fixture
def per_call(storage):
    """`per_call(lambda store: store.days(user_id))`: the repository, each call in its own transaction."""
    return lambda repository: PerCall(storage, repository)
