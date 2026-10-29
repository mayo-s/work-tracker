"""Admin endpoints: /api/admin/users, /api/admin/users/{user_id} and /api/admin/settings (admins only, else 403)."""

import sqlite3

import falcon
from spectree import Response

from src.modules.admin.schemas import AdminSettings, AdminUserInput, AdminUserView
from src.modules.auth.sessions import current_user
from src.modules.storage.database import Database
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.settings import registration_open, set_registration
from src.modules.storage.users import UserRepository
from src.utils.spec import spec

TAGS = ['Admin']
ID_PARAMETER = {'user_id': 'Id (UUID) of the user'}


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
        """All users in the order they registered, with role, status, registration and last login."""
        with self._database.transaction() as conn:
            _admin(req, conn)
            resp.media = [AdminUserView.of(user) for user in UserRepository(conn).all()]


class AdminUserItem:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(json=AdminUserInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_200=AdminUserView),
                   tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, user_id: str, json: AdminUserInput) -> None:
        """Change a user's role, or deactivate (their sessions end, their data is kept) or reactivate them.

        Nobody demotes or deactivates themselves (409), so an active admin always remains.
        """
        with self._database.transaction() as conn:
            users = UserRepository(conn)
            if user_id == _admin(req, conn) and (json.role != 'admin' or not json.active):
                raise ConflictError('You cannot demote or deactivate yourself; ask another admin')
            users.get(user_id)
            users.set_role(user_id, json.role)
            resp.media = AdminUserView.of(users.set_active(user_id, json.active))


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
