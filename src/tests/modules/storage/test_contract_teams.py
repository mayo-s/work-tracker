"""Teams, memberships, invitations, team services and the team view log: the same behaviour on SQLite and on
DynamoDB (moto)."""

import datetime as dt

import pytest

from src.models.catalog import Service
from src.models.teams import Auditor, ReportView, Team
from src.modules.storage.errors import ConflictError, NotFoundError
from src.tests.helpers import Clock
from src.tests.users import HANS

MONDAY = dt.datetime(2026, 11, 2, 9, 0)


@pytest.fixture
def clock():
    return Clock(MONDAY)


@pytest.fixture
def teams(per_call, clock):
    return per_call(lambda store: store.teams(clock))


@pytest.fixture
def invitations(per_call, clock):
    return per_call(lambda store: store.invitations(clock))


@pytest.fixture
def platform(teams):
    return teams.add(Team(name='Platform'))


@pytest.fixture
def hans(storage, klara_id):
    with storage.transaction() as store:
        return store.users().add(HANS, 'correct horse battery 9!').id


def accept(storage, clock, user_id, invitation_id):
    with storage.transaction() as store:
        return store.invitations(clock).accept(user_id, invitation_id, store.teams(clock))


def test_add_rename_and_list(teams, platform):
    teams.add(Team(name='Billing'))
    teams.rename(platform.model_copy(update={'name': 'Core'}))
    assert [team.name for team in teams.all()] == ['Billing', 'Core']


def test_names_are_unique_ignoring_case(teams, platform):
    with pytest.raises(ConflictError):
        teams.add(Team(name='platform'))


def test_a_renamed_team_frees_its_old_name(teams, platform):
    teams.rename(platform.model_copy(update={'name': 'Core'}))
    assert teams.add(Team(name='Platform')).name == 'Platform'


def test_unknown_team(teams):
    with pytest.raises(NotFoundError):
        teams.get(404)


def test_joining_another_team_leaves_the_first(teams, platform, clock, klara_id):
    billing = teams.add(Team(name='Billing'))
    teams.join(klara_id, platform.id)
    clock.now = MONDAY + dt.timedelta(days=3)
    teams.join(klara_id, billing.id)
    history = [(m.team_name, m.joined_on, m.left_on) for m in teams.history(klara_id)]
    assert history == [('Platform', dt.date(2026, 11, 2), dt.date(2026, 11, 5)), ('Billing', dt.date(2026, 11, 5), None)]
    assert (teams.membership(klara_id).team_name, teams.members(platform.id)) == ('Billing', [])


def test_members_with_their_account(teams, platform, klara_id, hans):
    teams.join(hans, platform.id)
    teams.join(klara_id, platform.id)
    assert [(member.username, member.joined_on) for member in teams.members(platform.id)] == [
        ('hans', dt.date(2026, 11, 2)), ('klara', dt.date(2026, 11, 2))]


def test_leaving_copies_the_team_services_in_use(per_call, teams, platform, hans):
    team_services = per_call(lambda store: store.team_services(platform.id))
    auth, mail, unused = (team_services.add(Service(short_name=name, name=f'{name.lower()}-service'))
                          for name in ('AUTH', 'MAIL', 'UNUSED'))
    services = per_call(lambda store: store.services(hans))
    own_mail = services.add(Service(short_name='mail'))
    teams.join(hans, platform.id)
    tickets = per_call(lambda store: store.tickets(hans))
    for key, service in (('TNG-1', auth), ('TNG-2', mail)):
        tickets.ensure(key)
        tickets.set_service(key, service.id)
    teams.leave(hans)
    personal = {service.short_name: service for service in services.all()}
    assert sorted(personal) == ['AUTH', 'mail']
    assert (tickets.get('TNG-1').service_id, tickets.get('TNG-2').service_id) == (personal['AUTH'].id, own_mail.id)
    assert personal['AUTH'].name == 'auth-service'
    assert len(team_services.all()) == 3  # the team keeps its services


def test_a_team_admin_is_a_member_with_that_team_role(teams, platform, hans):
    teams.join(hans, platform.id)
    assert teams.set_team_role(hans, 'team_admin').team_role == 'team_admin'
    assert [(member.username, member.team_role) for member in teams.members(platform.id)] == [('hans', 'team_admin')]
    assert teams.membership(hans).team_role == 'team_admin'


def test_the_team_role_ends_with_the_membership(teams, platform, hans):
    teams.join(hans, platform.id)
    teams.set_team_role(hans, 'team_admin')
    teams.leave(hans)
    teams.join(hans, platform.id)  # back again: a member, until made team admin again
    assert [membership.team_role for membership in teams.history(hans)] == ['team_admin', 'member']


def test_only_a_member_of_a_team_has_a_team_role(teams, hans):
    with pytest.raises(ConflictError, match='Only a member of a team has a team role'):
        teams.set_team_role(hans, 'team_admin')


def test_team_with_members_cannot_be_deleted(teams, platform, klara_id):
    teams.join(klara_id, platform.id)
    with pytest.raises(ConflictError):
        teams.delete(platform.id)


def test_deleted_team_stays_in_the_history_and_frees_its_name(per_call, teams, platform, invitations, klara_id):
    team_services = per_call(lambda store: store.team_services(platform.id))
    team_services.add(Service(short_name='AUTH'))
    invitations.invite(platform.id, 'hans.dampf@example.com', klara_id)
    teams.join(klara_id, platform.id)
    teams.leave(klara_id)
    teams.delete(platform.id)
    assert [m.team_name for m in teams.history(klara_id)] == ['Platform']
    assert (teams.all(), invitations.of_team(platform.id), team_services.all()) == ([], [], [])
    assert teams.add(Team(name='Platform')).id != platform.id


def test_invitations_do_not_tell_whether_the_user_exists(invitations, platform, klara_id):
    invitations.invite(platform.id, 'nobody@example.com', klara_id)
    invitations.invite(platform.id, ' Hans.Dampf@Example.com ', klara_id)
    invitations.invite(platform.id, 'hans.dampf@example.com', klara_id)  # already invited
    emails = [invitation.email for invitation in invitations.of_team(platform.id)]
    assert emails == ['nobody@example.com', 'Hans.Dampf@Example.com']
    assert {invitation.team_name for invitation in invitations.of_team(platform.id)} == {'Platform'}


def test_members_are_not_invited(teams, invitations, platform, klara_id):
    teams.join(klara_id, platform.id)
    invitations.invite(platform.id, 'KLARA.himmel@example.com', klara_id)
    assert invitations.of_team(platform.id) == []


def test_accepting_joins_and_declines_the_other_invitations(storage, clock, teams, invitations, platform, hans, klara_id):
    billing = teams.add(Team(name='Billing'))
    invitations.invite(platform.id, 'hans.dampf@example.com', klara_id)
    invitations.invite(billing.id, 'hans.dampf@example.com', klara_id)
    invitation = invitations.of_user(hans)[1]
    assert accept(storage, clock, hans, invitation.id).team_name == 'Billing'
    assert (invitations.of_user(hans), [member.username for member in teams.members(billing.id)]) == ([], ['hans'])
    assert invitations.of_team(platform.id) == []


def test_decline(invitations, platform, hans, klara_id):
    invitations.invite(platform.id, 'hans.dampf@example.com', klara_id)
    invitations.decline(hans, invitations.of_user(hans)[0].id)
    assert (invitations.of_team(platform.id), invitations.of_user(hans)) == ([], [])


def test_another_users_invitation_is_unknown(storage, clock, invitations, platform, hans, klara_id):
    invitations.invite(platform.id, 'hans.dampf@example.com', klara_id)
    invitation_id = invitations.of_user(hans)[0].id
    with pytest.raises(NotFoundError):
        accept(storage, clock, klara_id, invitation_id)


def test_invitations_of_a_deleted_team_are_gone(teams, invitations, platform, hans, klara_id):
    invitations.invite(platform.id, 'hans.dampf@example.com', klara_id)
    teams.delete(platform.id)
    assert invitations.of_user(hans) == []


def test_withdraw(invitations, platform, hans, klara_id):
    invitations.invite(platform.id, 'hans.dampf@example.com', klara_id)
    invitations.withdraw(platform.id, invitations.of_team(platform.id)[0].id)
    assert (invitations.of_team(platform.id), invitations.of_user(hans)) == ([], [])


def test_withdraw_unknown_invitation(invitations, platform):
    with pytest.raises(NotFoundError):
        invitations.withdraw(platform.id, 404)


def test_members_choose_team_services_until_they_leave(per_call, teams, platform, klara_id, service_ids):
    per_call(lambda store: store.team_services(platform.id)).add(Service(short_name='AUTH'))
    services = per_call(lambda store: store.services(klara_id))
    teams.join(klara_id, platform.id)
    choices = [(choice.short_name, choice.team) for choice in services.choices()]
    assert choices[0] == ('AUTH', 'Platform') and len(choices) == 6
    teams.leave(klara_id)
    assert all(choice.team is None for choice in services.choices())


def test_only_services_of_the_own_team_can_be_assigned(per_call, teams, platform, klara_id):
    billing = teams.add(Team(name='Billing'))
    other = per_call(lambda store: store.team_services(billing.id)).add(Service(short_name='PAY'))
    own = per_call(lambda store: store.team_services(platform.id)).add(Service(short_name='AUTH'))
    teams.join(klara_id, platform.id)
    tickets = per_call(lambda store: store.tickets(klara_id))
    tickets.ensure('TNG-1')
    assert tickets.set_service('TNG-1', own.id).service_id == own.id
    with pytest.raises(ConflictError):
        tickets.set_service('TNG-1', other.id)


def test_deleting_a_team_service_unassigns_the_members_tickets(per_call, teams, platform, klara_id):
    team_services = per_call(lambda store: store.team_services(platform.id))
    auth = team_services.add(Service(short_name='AUTH'))
    teams.join(klara_id, platform.id)
    tickets = per_call(lambda store: store.tickets(klara_id))
    tickets.ensure('TNG-1')
    tickets.set_service('TNG-1', auth.id)
    team_services.delete(auth.id)
    assert tickets.get('TNG-1').service_id is None


def test_report_views_newest_first_with_the_viewers_name(per_call, klara_id, hans):
    views = per_call(lambda store: store.report_views())
    for minute, report in enumerate(('week', 'month', 'year')):
        views.add(ReportView(member_id=hans, viewer_id=klara_id, report=report, period='2026',
                             viewed_at=MONDAY + dt.timedelta(minutes=minute)))
    seen = [(view.report, view.viewer_name) for view in views.of_member(hans)]
    assert seen == [('year', 'Klara Himmel'), ('month', 'Klara Himmel'), ('week', 'Klara Himmel')]
    assert [view.report for view in views.of_member(hans, limit=2)] == ['year', 'month']
    assert views.of_member(klara_id) == []


def test_the_stays_of_a_team_keep_former_members(teams, clock, platform, hans, klara_id):
    teams.join(hans, platform.id)
    clock.now = MONDAY + dt.timedelta(days=2)
    teams.leave(hans)
    teams.join(klara_id, platform.id)
    clock.now = MONDAY + dt.timedelta(days=3)
    teams.join(hans, platform.id)
    stays = [(stay.user_id, stay.joined_on.day, stay.left_on and stay.left_on.day) for stay in teams.stays(platform.id)]
    assert stays == [(hans, 2, 4), (klara_id, 4, None), (hans, 5, None)]


@pytest.fixture
def auditors(per_call):
    return per_call(lambda store: store.auditors())


def auditor(team_id, user_id, until=None, by=None):
    return Auditor(team_id=team_id, user_id=user_id, until=until, assigned_by=by or user_id, assigned_at=MONDAY)


def test_auditors_are_assigned_changed_and_removed(auditors, platform, hans, klara_id):
    auditors.assign(auditor(platform.id, hans, by=klara_id))
    auditors.assign(auditor(platform.id, hans, until=dt.date(2026, 11, 30), by=klara_id))  # a new end date
    [assigned] = auditors.all()
    assert (assigned.team_name, assigned.user_name, assigned.until) == ('Platform', 'Hans Dampf', dt.date(2026, 11, 30))
    assert [item.user_id for item in auditors.of_team(platform.id)] == [hans]
    assert [item.team_id for item in auditors.of_user(hans)] == [platform.id]
    auditors.remove(platform.id, hans)
    assert auditors.all() == []
    with pytest.raises(NotFoundError, match='No such auditor'):
        auditors.remove(platform.id, hans)


def test_an_assignment_ends_after_its_last_day():
    assigned = auditor('team', 'hans', until=dt.date(2026, 11, 30))
    assert (assigned.active(dt.date(2026, 11, 30)), assigned.active(dt.date(2026, 12, 1))) == (True, False)
    assert auditor('team', 'hans').active(dt.date(2099, 1, 1))


def test_deleting_a_team_ends_its_auditors(teams, auditors, platform, hans):
    auditors.assign(auditor(platform.id, hans))
    teams.delete(platform.id)
    assert (auditors.all(), auditors.of_user(hans)) == ([], [])


def test_all_teams_with_the_deleted_ones(teams, platform, clock):
    teams.add(Team(name='Billing'))
    clock.now += dt.timedelta(hours=1)
    teams.delete(platform.id)
    assert [(team.name, team.deleted_at) for team in teams.with_deleted()] == [
        ('Platform', clock.now), ('Billing', None)]  # in the order they were created


def test_all_open_invitations(teams, invitations, platform, clock, klara_id):
    billing = teams.add(Team(name='Billing'))
    invitations.invite(billing.id, 'hans.dampf@example.com', klara_id)
    clock.now += dt.timedelta(minutes=1)
    invitations.invite(platform.id, 'rainer.zufall@example.com', klara_id)
    assert [(invitation.team_name, invitation.email) for invitation in invitations.all()] == [
        ('Billing', 'hans.dampf@example.com'), ('Platform', 'rainer.zufall@example.com')]


def test_all_report_views_oldest_first(per_call, klara_id, hans):
    views = per_call(lambda store: store.report_views())
    views.add(ReportView(member_id=hans, viewer_id=klara_id, report='week', period='2026-W45', viewed_at=MONDAY))
    views.add(ReportView(member_id=klara_id, viewer_id=hans, report='dashboard', viewed_at=MONDAY - dt.timedelta(days=1)))
    assert [(view.member_id, view.viewer_name, view.report) for view in views.all()] == [
        (klara_id, 'Hans Dampf', 'dashboard'), (hans, 'Klara Himmel', 'week')]
