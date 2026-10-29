import datetime as dt

import pytest

from src.models.catalog import Service
from src.models.teams import Team
from src.modules.storage.catalog import ServiceRepository, TeamServiceRepository
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.teams import InvitationRepository, TeamRepository
from src.modules.storage.tickets import TicketRepository
from src.modules.storage.users import UserRepository
from src.tests.users import HANS, PASSWORD, USER

MONDAY = dt.datetime(2026, 11, 2, 9, 0)


class Clock:
    def __init__(self):
        self.now = MONDAY

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def teams(conn, clock):
    return TeamRepository(conn, clock)


@pytest.fixture
def invitations(conn, clock):
    return InvitationRepository(conn, clock)


@pytest.fixture
def platform(teams):
    return teams.add(Team(name='Platform'))


@pytest.fixture
def hans(conn):
    return UserRepository(conn).add(HANS, PASSWORD).id


def test_add_rename_and_list(teams, platform):
    teams.add(Team(name='Billing'))
    teams.rename(platform.model_copy(update={'name': 'Core'}))
    assert [team.name for team in teams.all()] == ['Billing', 'Core']


def test_names_are_unique_ignoring_case(teams, platform):
    with pytest.raises(ConflictError):
        teams.add(Team(name='platform'))


def test_joining_another_team_leaves_the_first(teams, platform, clock):
    billing = teams.add(Team(name='Billing'))
    teams.join(USER, platform.id)
    clock.now = MONDAY + dt.timedelta(days=3)
    teams.join(USER, billing.id)
    history = [(m.team_name, m.joined_on, m.left_on) for m in teams.history(USER)]
    assert history == [('Platform', dt.date(2026, 11, 2), dt.date(2026, 11, 5)), ('Billing', dt.date(2026, 11, 5), None)]
    assert (teams.membership(USER).team_name, teams.members(platform.id)) == ('Billing', [])


def test_leaving_copies_the_team_services_in_use(conn, teams, platform, hans):
    team_services = TeamServiceRepository(conn, platform.id)
    auth, mail, unused = (team_services.add(Service(short_name=name, name=f'{name.lower()}-service'))
                          for name in ('AUTH', 'MAIL', 'UNUSED'))
    own_mail = ServiceRepository(conn, hans).add(Service(short_name='mail'))
    teams.join(hans, platform.id)
    tickets = TicketRepository(conn, hans)
    for key, service in (('TNG-1', auth), ('TNG-2', mail)):
        tickets.ensure(key)
        tickets.set_service(key, service.id)
    teams.leave(hans)
    personal = {service.short_name: service for service in ServiceRepository(conn, hans).all()}
    assert sorted(personal) == ['AUTH', 'mail']
    assert (tickets.get('TNG-1').service_id, tickets.get('TNG-2').service_id) == (personal['AUTH'].id, own_mail.id)
    assert personal['AUTH'].name == 'auth-service'
    assert len(team_services.all()) == 3  # the team keeps its services


def test_a_team_admin_leaving_becomes_a_user(conn, teams, platform, hans):
    users = UserRepository(conn)
    teams.join(hans, platform.id)
    users.set_role(hans, 'team_admin')
    teams.leave(hans)
    assert (users.get(hans).role, teams.membership(hans)) == ('user', None)


def test_team_with_members_cannot_be_deleted(teams, platform):
    teams.join(USER, platform.id)
    with pytest.raises(ConflictError):
        teams.delete(platform.id)


def test_deleted_team_stays_in_the_history_and_frees_its_name(conn, teams, platform, invitations):
    TeamServiceRepository(conn, platform.id).add(Service(short_name='AUTH'))
    invitations.invite(platform.id, 'hans.dampf@example.com', USER)
    teams.join(USER, platform.id)
    teams.leave(USER)
    teams.delete(platform.id)
    assert [m.team_name for m in teams.history(USER)] == ['Platform']
    assert (teams.all(), invitations.of_team(platform.id), TeamServiceRepository(conn, platform.id).all()) == ([], [], [])
    assert teams.add(Team(name='Platform')).id != platform.id


def test_invitations_do_not_tell_whether_the_user_exists(invitations, platform):
    invitations.invite(platform.id, 'nobody@example.com', USER)
    invitations.invite(platform.id, ' Hans.Dampf@Example.com ', USER)
    invitations.invite(platform.id, 'hans.dampf@example.com', USER)  # already invited
    emails = [invitation.email for invitation in invitations.of_team(platform.id)]
    assert emails == ['nobody@example.com', 'Hans.Dampf@Example.com']


def test_members_are_not_invited(teams, invitations, platform):
    teams.join(USER, platform.id)
    invitations.invite(platform.id, 'KLARA.himmel@example.com', USER)
    assert invitations.of_team(platform.id) == []


def test_accepting_joins_and_declines_the_other_invitations(teams, invitations, platform, hans):
    billing = teams.add(Team(name='Billing'))
    invitations.invite(platform.id, 'hans.dampf@example.com', USER)
    invitations.invite(billing.id, 'hans.dampf@example.com', USER)
    invitation = invitations.of_user(hans)[1]
    assert invitations.accept(hans, invitation.id, teams).team_name == 'Billing'
    assert (invitations.of_user(hans), [member.username for member in teams.members(billing.id)]) == ([], ['hans'])


def test_decline(invitations, platform, hans):
    invitations.invite(platform.id, 'hans.dampf@example.com', USER)
    invitations.decline(hans, invitations.of_user(hans)[0].id)
    assert invitations.of_team(platform.id) == []


def test_another_users_invitation_is_unknown(teams, invitations, platform, hans):
    invitations.invite(platform.id, 'hans.dampf@example.com', USER)
    invitation_id = invitations.of_user(hans)[0].id
    with pytest.raises(NotFoundError):
        invitations.accept(USER, invitation_id, teams)


def test_withdraw(invitations, platform):
    invitations.invite(platform.id, 'hans.dampf@example.com', USER)
    invitations.withdraw(platform.id, invitations.of_team(platform.id)[0].id)
    assert invitations.of_team(platform.id) == []


def test_members_choose_team_services_until_they_leave(conn, teams, platform):
    TeamServiceRepository(conn, platform.id).add(Service(short_name='AUTH'))
    services = ServiceRepository(conn, USER)
    teams.join(USER, platform.id)
    choices = [(choice.short_name, choice.team) for choice in services.choices()]
    assert choices[0] == ('AUTH', 'Platform') and len(choices) == 6
    teams.leave(USER)
    assert all(choice.team is None for choice in services.choices())


def test_only_services_of_the_own_team_can_be_assigned(conn, teams, platform):
    billing = teams.add(Team(name='Billing'))
    other = TeamServiceRepository(conn, billing.id).add(Service(short_name='PAY'))
    teams.join(USER, platform.id)
    TicketRepository(conn, USER).ensure('TNG-1')
    with pytest.raises(ConflictError):
        TicketRepository(conn, USER).set_service('TNG-1', other.id)
