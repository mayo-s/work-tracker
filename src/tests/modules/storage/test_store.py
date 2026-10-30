import inspect
from typing import Protocol

import pytest

from src.modules.storage import store
from src.modules.storage.catalog import ActivityTypeRepository, ServiceRepository, TeamServiceRepository
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.pto_years import PtoYearRepository
from src.modules.storage.schedules import ScheduleRepository
from src.modules.storage.sqlite import SqliteStorage, SqliteStore
from src.modules.storage.teams import InvitationRepository, ReportViewLog, TeamRepository
from src.modules.storage.tickets import TicketRepository
from src.modules.storage.users import LoginAttempts, SessionRepository, UserRepository
from src.tests.users import USER

IMPLEMENTATIONS = [
    (store.Days, DayRepository), (store.Entries, EntryRepository), (store.Tickets, TicketRepository),
    (store.Services, ServiceRepository), (store.Services, TeamServiceRepository), (store.Catalog, ActivityTypeRepository),
    (store.WorkSchedules, ScheduleRepository), (store.PtoYears, PtoYearRepository), (store.Users, UserRepository),
    (store.Sessions, SessionRepository), (store.Attempts, LoginAttempts), (store.Teams, TeamRepository),
    (store.Invitations, InvitationRepository), (store.ReportViews, ReportViewLog), (store.Store, SqliteStore),
    (store.Storage, SqliteStorage),
]


def _methods(protocol: type[Protocol]) -> list[str]:
    return [name for name in dir(protocol) if not name.startswith('_') and inspect.isfunction(getattr(protocol, name))]


def _parameters(function: object) -> list[tuple[str, object, object]]:
    """Names, kinds and defaults; the annotations may name the implementation instead of the interface."""
    return [(p.name, p.kind, p.default) for p in inspect.signature(function).parameters.values()]


@pytest.mark.parametrize('protocol, implementation', IMPLEMENTATIONS)
def test_sqlite_backend_implements_the_interfaces(protocol, implementation):
    for name in _methods(protocol):
        assert _parameters(getattr(implementation, name)) == _parameters(getattr(protocol, name)), name


def test_the_sqlite_store_hands_out_repositories_of_its_transaction(database):
    with SqliteStorage(database).transaction() as sqlite_store:
        assert sqlite_store.users().get(USER).username == 'klara'
        assert sqlite_store.setup_done(USER)
