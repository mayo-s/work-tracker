import inspect
from typing import Protocol

import pytest

from src.modules.storage import store
from src.modules.storage.catalog import ActivityTypeRepository, ServiceRepository, TeamServiceRepository
from src.modules.storage.days import DayRepository
from src.modules.storage.dynamodb.catalog import DynamoActivityTypes, DynamoServices, DynamoTeamServices
from src.modules.storage.dynamodb.days import DynamoDays
from src.modules.storage.dynamodb.entries import DynamoEntries
from src.modules.storage.dynamodb.schedules import DynamoPtoYears, DynamoSchedules
from src.modules.storage.dynamodb.storage import DynamoStorage, DynamoStore
from src.modules.storage.dynamodb.teams import DynamoInvitations, DynamoReportViews, DynamoTeams
from src.modules.storage.dynamodb.tickets import DynamoTickets
from src.modules.storage.dynamodb.users import DynamoAttempts, DynamoSessions, DynamoUsers
from src.modules.storage.entries import EntryRepository
from src.modules.storage.pto_years import PtoYearRepository
from src.modules.storage.schedules import ScheduleRepository
from src.modules.storage.sqlite import SqliteStorage, SqliteStore
from src.modules.storage.teams import InvitationRepository, ReportViewLog, TeamRepository
from src.modules.storage.tickets import TicketRepository
from src.modules.storage.users import LoginAttempts, SessionRepository, UserRepository

IMPLEMENTATIONS = [
    (store.Days, DayRepository), (store.Entries, EntryRepository), (store.Tickets, TicketRepository),
    (store.Services, ServiceRepository), (store.Services, TeamServiceRepository), (store.Catalog, ActivityTypeRepository),
    (store.WorkSchedules, ScheduleRepository), (store.PtoYears, PtoYearRepository), (store.Users, UserRepository),
    (store.Sessions, SessionRepository), (store.Attempts, LoginAttempts), (store.Teams, TeamRepository),
    (store.Invitations, InvitationRepository), (store.ReportViews, ReportViewLog), (store.Store, SqliteStore),
    (store.Storage, SqliteStorage),
]
DYNAMODB = [
    (store.Days, DynamoDays), (store.Entries, DynamoEntries), (store.Tickets, DynamoTickets),
    (store.Services, DynamoServices), (store.Catalog, DynamoActivityTypes), (store.Users, DynamoUsers),
    (store.Services, DynamoTeamServices), (store.WorkSchedules, DynamoSchedules), (store.PtoYears, DynamoPtoYears),
    (store.Sessions, DynamoSessions), (store.Attempts, DynamoAttempts), (store.Teams, DynamoTeams),
    (store.Invitations, DynamoInvitations), (store.ReportViews, DynamoReportViews), (store.Store, DynamoStore),
    (store.Storage, DynamoStorage),
]


def _methods(protocol: type[Protocol]) -> list[str]:
    return [name for name in dir(protocol) if not name.startswith('_') and inspect.isfunction(getattr(protocol, name))]


def _parameters(function: object) -> list[tuple[str, object, object]]:
    """Names, kinds and defaults; the annotations may name the implementation instead of the interface."""
    return [(p.name, p.kind, p.default) for p in inspect.signature(function).parameters.values()]


@pytest.mark.parametrize('backend', [IMPLEMENTATIONS, DYNAMODB], ids=['sqlite', 'dynamodb'])
def test_the_backend_implements_the_interfaces(backend):
    differing = [f'{implementation.__name__}.{name}' for protocol, implementation in backend for name in _methods(protocol)
                 if _parameters(getattr(implementation, name)) != _parameters(getattr(protocol, name))]
    assert differing == []
