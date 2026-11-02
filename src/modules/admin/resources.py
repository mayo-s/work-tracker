"""Admin endpoints (403 for others): /api/admin/users (root and admins), /api/admin/teams, each also by id (admins),
and /api/admin/settings (root).

Root appoints and removes admins and helps them (one-time password, deactivate, reactivate); admins help users and
team admins, give team roles and manage teams (SPEC 5.7)."""

import datetime as dt
from collections.abc import Callable

import falcon
from spectree import Response

from src.lib.passwords import one_time_password
from src.modules.admin.schemas import AdminSettings, AdminTeamView, AdminUserInput, AdminUserView, OneTimePasswordView
from src.modules.auth.sessions import current_user
from src.models.teams import Membership
from src.models.users import Role, User
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.store import Storage, Store
from src.modules.teams.schemas import TeamInput
from src.utils.spec import spec

TAGS = ['Admin']
ID_PARAMETER = {'user_id': 'Id (UUID) of the user'}
TEAM_PARAMETER = {'team_id': 'Id of the team'}


STAFF: tuple[Role, ...] = ('root', 'admin')
ONLY = {STAFF: 'Only root and admins may do this', ('admin',): 'Only admins may do this', ('root',): 'Only root may do this'}


def _staff(req: falcon.Request, store: Store, roles: tuple[Role, ...] = STAFF) -> User:
    """The current user if their role is one of `roles`; 403 otherwise."""
    try:
        user = store.users().get(current_user(req))
    except NotFoundError:  # e.g. no user yet with the login off
        user = None
    if user is None or user.role not in roles:
        raise falcon.HTTPForbidden(description=ONLY[roles])
    return user


def _helps(target: User) -> Role:
    """Who helps the user (one-time password, deactivate, reactivate): root an admin, an admin anyone else."""
    return 'root' if target.role == 'admin' else 'admin'


def _check_help(actor: User, target: User, action: str) -> None:
    if actor.role != _helps(target):
        who = 'root for admins' if target.role == 'admin' else 'admins for users'
        raise falcon.HTTPForbidden(description=f'Only {who} may {action}')


class AdminUserCollection:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response('HTTP_403', HTTP_200=list[AdminUserView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """All users in the order they registered, with role, status, registration, last login and team."""
        with self._storage.transaction() as store:
            _staff(req, store)
            resp.media = [_view(store, user.id) for user in store.users().all()]


class AdminUserItem:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(json=AdminUserInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_200=AdminUserView),
                   tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, user_id: str, json: AdminUserInput) -> None:
        """Change a user's role or team role, or deactivate (their sessions end, their data is kept) or reactivate them.

        Only root appoints and removes admins and deactivates or reactivates them; only admins give team roles and
        deactivate or reactivate everyone else (403 otherwise). Nobody demotes or deactivates themselves (409), and root
        stays as it is (409). Only a member of a team has a team role (409); a team admin manages that team. Nobody
        changes their own team role (409), so no admin makes themselves the team admin who sees the members' reports.
        """
        with self._storage.transaction() as store:
            users, teams = store.users(), store.teams()
            actor, target = _staff(req, store), users.get(user_id)
            if target.role == 'root':
                raise ConflictError('Root stays root and active')
            membership = teams.membership(user_id)
            if user_id == actor.id:
                _check_own_change(json, membership)
            _check_rights(actor, target, json, membership)
            if json.team_role is not None and (json.team_role == 'team_admin' or membership):
                teams.set_team_role(user_id, json.team_role)
            users.set_role(user_id, json.role)
            users.set_active(user_id, json.active)
            resp.media = _view(store, user_id)


def _check_rights(actor: User, target: User, json: AdminUserInput, membership: Membership | None) -> None:
    if json.role != target.role and actor.role != 'root':
        raise falcon.HTTPForbidden(description='Only root appoints and removes admins')
    if _team_role_changes(json, membership) and actor.role != 'admin':
        raise falcon.HTTPForbidden(description='Only admins give team roles')
    if json.active != target.active:
        _check_help(actor, target, 'deactivate or reactivate them')


def _team_role_changes(json: AdminUserInput, membership: Membership | None) -> bool:
    return json.team_role is not None and json.team_role != (membership.team_role if membership else None)


def _check_own_change(json: AdminUserInput, membership: Membership | None) -> None:
    if json.role != 'admin' or not json.active:
        raise ConflictError('You cannot demote or deactivate yourself; ask another admin')
    if _team_role_changes(json, membership):
        raise ConflictError('You cannot change your own team role; ask another admin')


class AdminOneTimePassword:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_201=OneTimePasswordView), tags=TAGS,
                   path_parameter_descriptions=ID_PARAMETER)
    def on_post(self, req: falcon.Request, resp: falcon.Response, user_id: str) -> None:
        """Set a one-time password for a user who forgot theirs, shown only in this answer: their sessions end, and at
        the next login they choose their own password before anything else.

        Root sets it for admins, admins for everyone else (403 otherwise). Not for the own account nor root's (409):
        those passwords are changed in the settings.
        """
        with self._storage.transaction() as store:
            actor = _staff(req, store)
            if user_id == actor.id:
                raise ConflictError('Change your own password in your settings')
            target = store.users().get(user_id)
            if target.role == 'root':
                raise ConflictError("Root's password is changed in its own settings")
            _check_help(actor, target, 'set one-time passwords')
            password = one_time_password()
            store.users().set_one_time_password(user_id, password)
        resp.status = falcon.HTTP_201
        resp.media = OneTimePasswordView(password=password)


class AdminTeamCollection:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response('HTTP_403', HTTP_200=list[AdminTeamView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """All teams with their number of members and their team admins."""
        with self._storage.transaction() as store:
            _staff(req, store, ('admin',))
            resp.media = [_team_view(store, team.id) for team in store.teams().all()]

    @spec.validate(json=TeamInput, resp=Response('HTTP_403', 'HTTP_409', HTTP_201=AdminTeamView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: TeamInput) -> None:
        """Create a team; names are unique, ignoring case (409)."""
        with self._storage.transaction() as store:
            _staff(req, store, ('admin',))
            resp.media = _team_view(store, store.teams().add(json.to_team()).id)
        resp.status = falcon.HTTP_201


class AdminTeamItem:
    def __init__(self, storage: Storage, clock: Callable[[], dt.datetime] = dt.datetime.now) -> None:
        self._storage = storage
        self._clock = clock

    @spec.validate(json=TeamInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_200=AdminTeamView), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, team_id: str, json: TeamInput) -> None:
        """Rename a team."""
        with self._storage.transaction() as store:
            _staff(req, store, ('admin',))
            store.teams().rename(json.to_team(team_id))
            resp.media = _team_view(store, team_id)

    @spec.validate(resp=Response('HTTP_204', 'HTTP_403', 'HTTP_404', 'HTTP_409'), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, team_id: str) -> None:
        """Delete a team without members (409 otherwise); its invitations and services go with it, the membership
        history keeps it."""
        with self._storage.transaction() as store:
            _staff(req, store, ('admin',))
            store.teams(self._clock).delete(team_id)
        resp.status = falcon.HTTP_204


class AdminSettingsResource:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @spec.validate(resp=Response('HTTP_403', HTTP_200=AdminSettings), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """App-wide settings: whether new users can register."""
        with self._storage.transaction() as store:
            _staff(req, store, ('root',))
            resp.media = AdminSettings(registration=store.registration_open())

    @spec.validate(json=AdminSettings, resp=Response('HTTP_403', HTTP_200=AdminSettings), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: AdminSettings) -> None:
        """Switch registration on or off; the login page links to /register only while it is on."""
        with self._storage.transaction() as store:
            _staff(req, store, ('root',))
            store.set_registration(json.registration)
        resp.media = json


def _view(store: Store, user_id: str) -> AdminUserView:
    return AdminUserView.of(store.users().get(user_id), store.teams().membership(user_id))


def _team_view(store: Store, team_id: str) -> AdminTeamView:
    teams = store.teams()
    return AdminTeamView.of(teams.get(team_id), teams.members(team_id))
