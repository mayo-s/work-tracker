"""Admin endpoints: /api/admin/users, /api/admin/teams (each also by id) and /api/admin/settings (admins only, else
403)."""

import datetime as dt
import sqlite3
from collections.abc import Callable

import falcon
from spectree import Response

from src.modules.admin.schemas import AdminSettings, AdminTeamView, AdminUserInput, AdminUserView
from src.modules.auth.sessions import current_user
from src.modules.storage.database import Database
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.settings import registration_open, set_registration
from src.modules.storage.teams import TeamRepository
from src.modules.storage.users import UserRepository
from src.modules.teams.schemas import TeamInput
from src.utils.spec import spec

TAGS = ['Admin']
ID_PARAMETER = {'user_id': 'Id (UUID) of the user'}
TEAM_PARAMETER = {'team_id': 'Id of the team'}


def _admin(req: falcon.Request, conn: sqlite3.Connection) -> str:
    """The current user if they are an admin; 403 otherwise."""
    user_id = current_user(req)
    try:
        is_admin = UserRepository(conn).get(user_id).role == 'admin'
    except NotFoundError:  # e.g. no user yet with the login off
        is_admin = False
    if not is_admin:
        raise falcon.HTTPForbidden(description='Only admins may do this')
    return user_id


class AdminUserCollection:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response('HTTP_403', HTTP_200=list[AdminUserView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """All users in the order they registered, with role, status, registration, last login and team."""
        with self._database.transaction() as conn:
            _admin(req, conn)
            resp.media = [_view(conn, user.id) for user in UserRepository(conn).all()]


class AdminUserItem:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(json=AdminUserInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_200=AdminUserView),
                   tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, user_id: str, json: AdminUserInput) -> None:
        """Change a user's role, or deactivate (their sessions end, their data is kept) or reactivate them.

        Nobody demotes or deactivates themselves (409), so an active admin always remains. Only a member of a team can be
        a team admin (409); they manage that team.
        """
        with self._database.transaction() as conn:
            users = UserRepository(conn)
            if user_id == _admin(req, conn) and (json.role != 'admin' or not json.active):
                raise ConflictError('You cannot demote or deactivate yourself; ask another admin')
            users.get(user_id)
            if json.role == 'team_admin' and TeamRepository(conn).membership(user_id) is None:
                raise ConflictError('Only a member of a team can be a team admin; invite them first')
            users.set_role(user_id, json.role)
            users.set_active(user_id, json.active)
            resp.media = _view(conn, user_id)


class AdminTeamCollection:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response('HTTP_403', HTTP_200=list[AdminTeamView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """All teams with their number of members and their team admins."""
        with self._database.transaction() as conn:
            _admin(req, conn)
            resp.media = [_team_view(conn, team.id) for team in TeamRepository(conn).all()]

    @spec.validate(json=TeamInput, resp=Response('HTTP_403', 'HTTP_409', HTTP_201=AdminTeamView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: TeamInput) -> None:
        """Create a team; names are unique, ignoring case (409)."""
        with self._database.transaction() as conn:
            _admin(req, conn)
            resp.media = _team_view(conn, TeamRepository(conn).add(json.to_team()).id)
        resp.status = falcon.HTTP_201


class AdminTeamItem:
    def __init__(self, database: Database, clock: Callable[[], dt.datetime] = dt.datetime.now) -> None:
        self._database = database
        self._clock = clock

    @spec.validate(json=TeamInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_200=AdminTeamView), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, team_id: int, json: TeamInput) -> None:
        """Rename a team."""
        with self._database.transaction() as conn:
            _admin(req, conn)
            TeamRepository(conn).rename(json.to_team(team_id))
            resp.media = _team_view(conn, team_id)

    @spec.validate(resp=Response('HTTP_204', 'HTTP_403', 'HTTP_404', 'HTTP_409'), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, team_id: int) -> None:
        """Delete a team without members (409 otherwise); its invitations and services go with it, the membership
        history keeps it."""
        with self._database.transaction() as conn:
            _admin(req, conn)
            TeamRepository(conn, self._clock).delete(team_id)
        resp.status = falcon.HTTP_204


class AdminSettingsResource:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response('HTTP_403', HTTP_200=AdminSettings), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """App-wide settings: whether new users can register."""
        with self._database.transaction() as conn:
            _admin(req, conn)
            resp.media = AdminSettings(registration=registration_open(conn))

    @spec.validate(json=AdminSettings, resp=Response('HTTP_403', HTTP_200=AdminSettings), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: AdminSettings) -> None:
        """Switch registration on or off; the login page links to /register only while it is on."""
        with self._database.transaction() as conn:
            _admin(req, conn)
            set_registration(conn, json.registration)
        resp.media = json


def _view(conn: sqlite3.Connection, user_id: str) -> AdminUserView:
    membership = TeamRepository(conn).membership(user_id)
    return AdminUserView.of(UserRepository(conn).get(user_id), membership.team_name if membership else None)


def _team_view(conn: sqlite3.Connection, team_id: int) -> AdminTeamView:
    teams = TeamRepository(conn)
    return AdminTeamView.of(teams.get(team_id), [(member.username, member.role) for member in teams.members(team_id)])
