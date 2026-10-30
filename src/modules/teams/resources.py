"""Team endpoints: /api/teams/{team_id} with its members, invitations and services (for the admin and the team's
admins), /api/team (the user's own team and invitations) and /api/service-choices."""

import datetime as dt
from collections.abc import Callable

import falcon
from spectree import Response

from src.models.catalog import Service, ServiceChoice
from src.models.teams import Member
from src.modules.auth.sessions import current_user
from src.modules.catalog.resources import ServiceInput
from src.modules.storage.errors import NotFoundError
from src.modules.storage.store import Storage, Store
from src.modules.teams.schemas import (
    InvitationInput, InvitationSent, InvitationView, MemberView, MyInvitationView, MyTeamView, ReportViewEntry, TeamPageView,
    TeamRef,
)
from src.utils.spec import spec

TAGS = ['Teams']
TEAM_PARAMETER = {'team_id': 'Id of the team'}
INVITED = 'If a user with this e-mail address exists, they find the invitation in their settings'


def team_admin_of(req: falcon.Request, store: Store, team_id: int) -> str:
    """The current user if they may manage the team: the admin, or an admin of this team; 403 otherwise."""
    user_id = current_user(req)
    try:
        role = store.users().get(user_id).role
    except NotFoundError:  # e.g. no user yet with the login off
        role = None
    membership = store.teams().membership(user_id)
    own_team = role == 'team_admin' and membership is not None and membership.team_id == team_id
    if role != 'admin' and not own_team:
        raise falcon.HTTPForbidden(description='Only the admin and the team admins of this team may do this')
    store.teams().get(team_id)
    return user_id


class _TeamResource:
    def __init__(self, storage: Storage, clock: Callable[[], dt.datetime] = dt.datetime.now) -> None:
        self._storage = storage
        self._clock = clock


class TeamItem(_TeamResource):
    @spec.validate(resp=Response('HTTP_403', 'HTTP_404', HTTP_200=TeamPageView), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, team_id: int) -> None:
        """The team with its members (accounts only) and open invitations."""
        with self._storage.transaction() as store:
            team_admin_of(req, store, team_id)
            teams = store.teams()
            resp.media = TeamPageView(
                id=team_id, name=teams.get(team_id).name,
                members=[MemberView.of(member) for member in teams.members(team_id)],
                invitations=[InvitationView.of(invitation) for invitation in store.invitations().of_team(team_id)])


class TeamInvitations(_TeamResource):
    @spec.validate(json=InvitationInput, resp=Response('HTTP_403', 'HTTP_404', HTTP_202=InvitationSent), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER)
    def on_post(self, req: falcon.Request, resp: falcon.Response, team_id: int, json: InvitationInput) -> None:
        """Invite the user with this exact e-mail address (ignoring case); the answer does not tell whether they exist."""
        with self._storage.transaction() as store:
            store.invitations(self._clock).invite(team_id, json.email, team_admin_of(req, store, team_id))
        resp.status = falcon.HTTP_202
        resp.media = InvitationSent(message=INVITED)


class TeamInvitationItem(_TeamResource):
    @spec.validate(resp=Response('HTTP_204', 'HTTP_403', 'HTTP_404'), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER | {'invitation_id': 'Id of the invitation'})
    def on_delete(self, req: falcon.Request, resp: falcon.Response, team_id: int, invitation_id: int) -> None:
        """Withdraw an open invitation."""
        with self._storage.transaction() as store:
            team_admin_of(req, store, team_id)
            store.invitations().withdraw(team_id, invitation_id)
        resp.status = falcon.HTTP_204


class TeamMemberItem(_TeamResource):
    @spec.validate(resp=Response('HTTP_204', 'HTTP_403', 'HTTP_404'), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER | {'user_id': 'Id (UUID) of the member'})
    def on_delete(self, req: falcon.Request, resp: falcon.Response, team_id: int, user_id: str) -> None:
        """Remove a member: the team services their tickets use become personal services; a team admin becomes a user."""
        with self._storage.transaction() as store:
            team_admin_of(req, store, team_id)
            teams = store.teams(self._clock)
            if user_id not in [member.user_id for member in teams.members(team_id)]:
                raise falcon.HTTPNotFound(description='No such member')
            teams.leave(user_id)
        resp.status = falcon.HTTP_204


class TeamServiceCollection(_TeamResource):
    @spec.validate(resp=Response('HTTP_403', 'HTTP_404', HTTP_200=list[Service]), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, team_id: int) -> None:
        """The team's services, which its members choose in entries."""
        with self._storage.transaction() as store:
            team_admin_of(req, store, team_id)
            resp.media = store.team_services(team_id).all()

    @spec.validate(json=ServiceInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_201=Service), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER)
    def on_post(self, req: falcon.Request, resp: falcon.Response, team_id: int, json: ServiceInput) -> None:
        """Add a team service."""
        with self._storage.transaction() as store:
            team_admin_of(req, store, team_id)
            resp.media = store.team_services(team_id).add(Service(**json.model_dump()))
        resp.status = falcon.HTTP_201


class TeamServiceItem(_TeamResource):
    _parameters = TEAM_PARAMETER | {'service_id': 'Id of the service'}

    @spec.validate(json=ServiceInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_200=Service), tags=TAGS,
                   path_parameter_descriptions=_parameters)
    def on_put(self, req: falcon.Request, resp: falcon.Response, team_id: int, service_id: int, json: ServiceInput) -> None:
        """Change a team service."""
        with self._storage.transaction() as store:
            team_admin_of(req, store, team_id)
            resp.media = store.team_services(team_id).update(Service(id=service_id, **json.model_dump()))

    @spec.validate(resp=Response('HTTP_204', 'HTTP_403', 'HTTP_404'), tags=TAGS, path_parameter_descriptions=_parameters)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, team_id: int, service_id: int) -> None:
        """Delete a team service; the members' tickets with it become "without service"."""
        with self._storage.transaction() as store:
            team_admin_of(req, store, team_id)
            store.team_services(team_id).delete(service_id)
        resp.status = falcon.HTTP_204


class MyTeam(_TeamResource):
    @spec.validate(resp=Response(HTTP_200=MyTeamView), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """The user's team (null without one) and their open invitations."""
        with self._storage.transaction() as store:
            resp.media = my_team(store, current_user(req))

    @spec.validate(resp=Response('HTTP_204'), tags=TAGS)
    def on_delete(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Leave the team: the team services the user's tickets use become personal services."""
        with self._storage.transaction() as store:
            store.teams(self._clock).leave(current_user(req))
        resp.status = falcon.HTTP_204


class MyInvitationAcceptance(_TeamResource):
    @spec.validate(resp=Response('HTTP_404', HTTP_200=MyTeamView), tags=TAGS,
                   path_parameter_descriptions={'invitation_id': 'Id of the invitation'})
    def on_post(self, req: falcon.Request, resp: falcon.Response, invitation_id: int) -> None:
        """Accept an invitation: join the team (leaving the current one); the other invitations are declined."""
        with self._storage.transaction() as store:
            user_id = current_user(req)
            store.invitations(self._clock).accept(user_id, invitation_id, store.teams(self._clock))
            resp.media = my_team(store, user_id)


class MyInvitationItem(_TeamResource):
    @spec.validate(resp=Response('HTTP_204', 'HTTP_404'), tags=TAGS,
                   path_parameter_descriptions={'invitation_id': 'Id of the invitation'})
    def on_delete(self, req: falcon.Request, resp: falcon.Response, invitation_id: int) -> None:
        """Decline an invitation."""
        with self._storage.transaction() as store:
            store.invitations().decline(current_user(req), invitation_id)
        resp.status = falcon.HTTP_204


class ServiceChoices:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response(HTTP_200=list[ServiceChoice]), tags=['Services'])
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """The services to choose in entries: the team's (`team`: its name) first, then the personal ones."""
        with self._storage.transaction() as store:
            resp.media = store.services(current_user(req)).choices()


def my_team(store: Store, user_id: str) -> MyTeamView:
    teams, users = store.teams(), store.users()
    membership = teams.membership(user_id)
    members = teams.members(membership.team_id) if membership else []
    return MyTeamView(
        team=TeamRef.of(membership) if membership else None,
        invitations=[MyInvitationView.of(invitation, users.get(invitation.invited_by))
                     for invitation in store.invitations().of_user(user_id)],
        team_admins=_team_admin_names(members, user_id),
        viewed_by=[ReportViewEntry.of(view) for view in store.report_views().of_member(user_id)],
    )


def _team_admin_names(members: list[Member], user_id: str) -> list[str]:
    """The team admins who can see the user's reports (not the user themselves)."""
    return [' '.join(filter(None, (member.first_name, member.last_name))) for member in members
            if member.role == 'team_admin' and member.user_id != user_id]
