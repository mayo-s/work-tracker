import datetime as dt
from decimal import Decimal

import pytest

from src.models.catalog import Service
from src.models.pto import PtoYear
from src.models.schedules import Schedule
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


@pytest.fixture
def service_ids(storage, klara_id):
    """Klara's services of the original setup, by short name."""
    services = [('O365', 'office-integration-service'), ('MSB', 'microsoft-bookings-service'), ('ImmoDrop', ''),
                ('HiS', 'history-service'), ('TTS', 'text-transformation-service')]
    with storage.transaction() as store:
        return {short_name: store.services(klara_id).add(Service(short_name=short_name, name=name)).id
                for short_name, name in services}


@pytest.fixture
def klara_schedule(storage, klara_id):
    """Klara's work schedule of the original setup: 40 h, Monday to Friday, Berlin, from 01.06.2024."""
    with storage.transaction() as store:
        return store.schedules(klara_id).replace_all(
            Schedule(valid_from=dt.date(2024, 6, 1), weekly_minutes=2400, work_days=[1, 2, 3, 4, 5]))


@pytest.fixture
def klara_pto_years(storage, klara_id):
    """Klara's PTO years of the original setup."""
    with storage.transaction() as store:
        store.pto_years(klara_id).replace_all([PtoYear(year=year, allowance=Decimal(days)) for year, days in (
            (2024, '17.5'), (2025, '31'), (2026, '31'), (2027, '30'))])
