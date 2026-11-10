"""Admin endpoints (403 for others): /api/admin/users and /api/admin/audit (root and admins), /api/admin/teams, each
also by id, and the auditors (admins), and /api/admin/settings, /api/admin/backup and /api/admin/restore (root). Every
change goes into the audit log.

Root appoints and removes admins and helps them (one-time password, deactivate, reactivate); admins help users and
team admins, give team roles and manage teams (SPEC 5.7)."""

import base64
import datetime as dt
from collections.abc import Callable

import falcon
from pydantic import ValidationError
from spectree import Response

from src.lib.passwords import one_time_password
from src.modules.admin.audit import AuditView, record
from src.modules.admin.schemas import (
    AdminSettings, AdminSettingsView, AdminTeamView, AdminUserInput, AdminUserView, AuditorInput, AuditorView,
    OneTimePasswordView,
)
from src.modules.auth.sessions import clear_session_cookie, current_user
from src.modules.auth.two_factor import required
from src.modules.backup.full import backup_file, make_backup, read_backup_file
from src.modules.backup.restore import BackupError, check_backup, restore_backup
from src.modules.backup.schemas import Backup, BackupInput, RestoreInput, RestoreSummary
from src.models.teams import Auditor, Membership
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


class _AdminResource:
    def __init__(self, storage: Storage, clock: Callable[[], dt.datetime] = dt.datetime.now) -> None:
        self._storage = storage
        self._clock = clock


class AdminUserCollection(_AdminResource):
    @spec.validate(resp=Response('HTTP_403', HTTP_200=list[AdminUserView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """All users in the order they registered, with role, status, registration, last login and team."""
        with self._storage.transaction() as store:
            _staff(req, store)
            resp.media = [_view(store, user.id) for user in store.users().all()]


class AdminUserItem(_AdminResource):
    @spec.validate(json=AdminUserInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_200=AdminUserView),
                   tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, user_id: str, json: AdminUserInput) -> None:
        """Change a user's role, team role or support role, or deactivate (their sessions end, their data is kept) or
        reactivate them.

        Only root appoints and removes admins and deactivates or reactivates them; only admins give team roles and the
        support role and deactivate or reactivate everyone else (403 otherwise). Nobody demotes or deactivates themselves
        (409), and root stays as it is (409). Only a member of a team has a team role (409); a team admin manages that
        team. Nobody changes their own team role (409), so no admin makes themselves the team admin who sees the
        members' reports; an admin may switch their own support role (audit-logged).
        """
        with self._storage.transaction() as store:
            users, teams = store.users(), store.teams()
            actor, target = _staff(req, store), users.get(user_id)
            if target.role == 'root':
                raise ConflictError('Root stays root and active')
            membership = teams.membership(user_id)
            if user_id == actor.id:
                _check_own_change(json, membership, target)
            _check_rights(actor, target, json, membership)
            now = self._clock()
            if _team_role_changes(json, membership):
                changed = teams.set_team_role(user_id, json.team_role)  # 409 without a team
                record(store, now, actor.id, 'team_role_changed', user_id, changed.team_id, changed.team_role)
            users.set_role(user_id, json.role)
            users.set_active(user_id, json.active)
            _record_role_and_status(store, now, actor.id, target, json)
            _switch_support(store, now, actor.id, target, json)
            resp.media = _view(store, user_id)


def _switch_support(store: Store, now: dt.datetime, actor_id: str, target: User, json: AdminUserInput) -> None:
    if _support_changes(json, target):
        store.users().set_support(target.id, json.support)
        record(store, now, actor_id, 'support_switched', target.id, detail='on' if json.support else 'off')


def _record_role_and_status(store: Store, now: dt.datetime, actor_id: str, target: User, json: AdminUserInput) -> None:
    if json.role != target.role:
        record(store, now, actor_id, 'role_changed', target.id, detail=json.role)
    if json.active != target.active:
        record(store, now, actor_id, 'reactivated' if json.active else 'deactivated', target.id)


def _check_rights(actor: User, target: User, json: AdminUserInput, membership: Membership | None) -> None:
    if json.role != target.role and actor.role != 'root':
        raise falcon.HTTPForbidden(description='Only root appoints and removes admins')
    if actor.role != 'admin':
        _check_admins_only(json, target, membership)
    if json.active != target.active:
        _check_help(actor, target, 'deactivate or reactivate them')


def _check_admins_only(json: AdminUserInput, target: User, membership: Membership | None) -> None:
    """What only admins give: team roles and the support role."""
    if _team_role_changes(json, membership):
        raise falcon.HTTPForbidden(description='Only admins give team roles')
    if _support_changes(json, target):
        raise falcon.HTTPForbidden(description='Only admins give the support role')


def _team_role_changes(json: AdminUserInput, membership: Membership | None) -> bool:
    return json.team_role is not None and json.team_role != (membership.team_role if membership else None)


def _support_changes(json: AdminUserInput, target: User) -> bool:
    return json.support is not None and json.support != target.support


def _check_own_change(json: AdminUserInput, membership: Membership | None, target: User) -> None:
    if json.role != 'admin' or not json.active:
        raise ConflictError('You cannot demote or deactivate yourself; ask another admin')
    if _team_role_changes(json, membership):
        raise ConflictError('You cannot change your own team role; ask another admin')


class AdminOneTimePassword(_AdminResource):
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
            record(store, self._clock(), actor.id, 'one_time_password', user_id)
        resp.status = falcon.HTTP_201
        resp.media = OneTimePasswordView(password=password)


class AdminTwoFactorReset(_AdminResource):
    @spec.validate(resp=Response('HTTP_204', 'HTTP_403', 'HTTP_404', 'HTTP_409'), tags=TAGS,
                   path_parameter_descriptions=ID_PARAMETER)
    def on_post(self, req: falcon.Request, resp: falcon.Response, user_id: str) -> None:
        """Switch a user's two-factor login off, e.g. after a lost phone: the next login needs no code (root and admins
        set it up again right after). Root for admins, admins for everyone else (403 otherwise); not for the own
        account, root's or one without two-factor login (409)."""
        with self._storage.transaction() as store:
            actor, users = _staff(req, store), store.users()
            if user_id == actor.id:
                raise ConflictError('Not for your own account: log in with a recovery code instead')
            target = users.get(user_id)
            if target.role == 'root':
                raise ConflictError("Root resets its own login with a new setup token")
            _check_help(actor, target, 'reset two-factor login')
            if not target.two_factor:
                raise ConflictError('Two-factor login is off already')
            users.save_two_factor(user_id, None)
            record(store, self._clock(), actor.id, 'two_factor_reset', user_id)
        resp.status = falcon.HTTP_204


class AdminTeamCollection(_AdminResource):
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
            actor = _staff(req, store, ('admin',))
            team = store.teams().add(json.to_team())
            record(store, self._clock(), actor.id, 'team_created', team_id=team.id)
            resp.media = _team_view(store, team.id)
        resp.status = falcon.HTTP_201


class AdminTeamItem(_AdminResource):
    @spec.validate(json=TeamInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_200=AdminTeamView), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, team_id: str, json: TeamInput) -> None:
        """Rename a team."""
        with self._storage.transaction() as store:
            actor, teams = _staff(req, store, ('admin',)), store.teams()
            former = teams.get(team_id).name
            teams.rename(json.to_team(team_id))
            if former != json.name:
                record(store, self._clock(), actor.id, 'team_renamed', team_id=team_id, detail=former)
            resp.media = _team_view(store, team_id)

    @spec.validate(resp=Response('HTTP_204', 'HTTP_403', 'HTTP_404', 'HTTP_409'), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, team_id: str) -> None:
        """Delete a team without members (409 otherwise); its invitations and services go with it, the membership
        history keeps it."""
        with self._storage.transaction() as store:
            actor = _staff(req, store, ('admin',))
            store.teams(self._clock).delete(team_id)
            record(store, self._clock(), actor.id, 'team_deleted', team_id=team_id)
        resp.status = falcon.HTTP_204


class AdminAuditorCollection(_AdminResource):
    @spec.validate(resp=Response('HTTP_403', HTTP_200=list[AuditorView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """All auditors by team: who has the team view of which team read-only, and until when."""
        with self._storage.transaction() as store:
            _staff(req, store, ('admin',))
            resp.media = [AuditorView.of(auditor) for auditor in store.auditors().all()]


class AdminAuditorItem(_AdminResource):
    @spec.validate(json=AuditorInput, resp=Response('HTTP_403', 'HTTP_404', 'HTTP_409', HTTP_200=AuditorView), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER | ID_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, team_id: str, user_id: str, json: AuditorInput) -> None:
        """Make a user or admin an auditor of the team, optionally until a day (inclusive), or change that day: they see
        the team view of everyone who was ever in the team, for the days of each stay, read-only. Not oneself and not
        root (409)."""
        with self._storage.transaction() as store:
            actor = _staff(req, store, ('admin',))
            store.teams().get(team_id)
            if store.users().get(user_id).role == 'root':
                raise ConflictError('Root tracks no work and audits no team')
            if user_id == actor.id:
                raise ConflictError('You cannot make yourself an auditor; ask another admin')
            now, auditors = self._clock(), store.auditors()
            auditors.assign(Auditor(team_id=team_id, user_id=user_id, until=json.until, assigned_by=actor.id, assigned_at=now))
            record(store, now, actor.id, 'auditor_assigned', user_id, team_id, json.until.isoformat() if json.until else '')
            resp.media = next(AuditorView.of(auditor) for auditor in auditors.of_team(team_id) if auditor.user_id == user_id)

    @spec.validate(resp=Response('HTTP_204', 'HTTP_403', 'HTTP_404'), tags=TAGS,
                   path_parameter_descriptions=TEAM_PARAMETER | ID_PARAMETER)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, team_id: str, user_id: str) -> None:
        """End an assignment: the auditor no longer sees the team."""
        with self._storage.transaction() as store:
            actor = _staff(req, store, ('admin',))
            store.auditors().remove(team_id, user_id)
            record(store, self._clock(), actor.id, 'auditor_removed', user_id, team_id)
        resp.status = falcon.HTTP_204


class AdminSettingsResource(_AdminResource):
    @spec.validate(resp=Response('HTTP_403', HTTP_200=AdminSettingsView), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """App-wide settings: whether new users can register, and whether a restore stopped halfway."""
        with self._storage.transaction() as store:
            _staff(req, store, ('root',))
            resp.media = AdminSettingsView(registration=store.registration_open(),
                                           restore_unfinished=store.restore_unfinished())

    @spec.validate(json=AdminSettings, resp=Response('HTTP_403', HTTP_200=AdminSettings), tags=TAGS)
    def on_put(self, req: falcon.Request, resp: falcon.Response, json: AdminSettings) -> None:
        """Switch registration on or off; the login page links to /register only while it is on."""
        with self._storage.transaction() as store:
            actor = _staff(req, store, ('root',))
            if store.registration_open() != json.registration:
                store.set_registration(json.registration)
                record(store, self._clock(), actor.id, 'registration_switched', detail='on' if json.registration else 'off')
        resp.media = json


class AdminBackupResource(_AdminResource):
    @spec.validate(json=BackupInput, resp=Response('HTTP_200', 'HTTP_403'), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: BackupInput) -> None:
        """Root only: the whole database as one file to download, e.g. `work-tracker-backup-2026-11-03.wtbackup`:
        all users (with password hashes and two-factor secrets), teams, memberships, invitations, auditors, every
        user's records with their history, the report view log, the audit log and the app settings. Not in it:
        sessions, remembered browsers, failed logins, the used setup tokens.

        Compressed (gzip) and encrypted with the passphrase (AES-256-GCM, key from scrypt), which is stored nowhere:
        without it the file cannot be restored. A header line before the encrypted part names the format and version.
        """
        now = self._clock()
        with self._storage.transaction() as store:
            actor = _staff(req, store, ('root',))
            backup = make_backup(store, now)
            record(store, now, actor.id, 'backup_made')
        resp.data = backup_file(backup, json.passphrase)
        resp.content_type = 'application/octet-stream'
        resp.downloadable_as = f'work-tracker-backup-{backup.made_at.date().isoformat()}.wtbackup'


PURGE_NEEDED = 'purge_required'  # the `code` of the 409 answer that asks to confirm the purge


class AdminRestoreResource(_AdminResource):
    @spec.validate(json=RestoreInput, resp=Response('HTTP_403', 'HTTP_409', 'HTTP_422', HTTP_200=RestoreSummary), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: RestoreInput) -> None:
        """Root only: restore the full backup from its file (base64) and passphrase. Everything but root goes first,
        then the backup comes in; root stays as it is (the backup's root is skipped), everyone else has their password
        and two-factor login from the backup, and all other sessions end. With `root_login`, root takes over the login of
        the backup's root instead (username, e-mail address, name, password, two-factor login): its sessions end too, and
        it logs in again with that login.

        Root without two-factor login gets here only while the database holds nobody else, and only takes over the
        backup's root login (403 otherwise), which comes with its own two-factor login.

        While anyone but root exists, only with `confirm` 'purge' (409 with the code `purge_required` otherwise). A
        wrong passphrase, a damaged file, another format, a newer version or a backup that does not hold together is
        refused before anything is written (422). On DynamoDB the restore writes chunks; one that stops halfway leaves
        only root using the app until restoring the file again finishes it.
        """
        with self._storage.transaction() as store:
            _check_two_factor(_staff(req, store, ('root',)), json.root_login)  # before the costly decryption
        backup = _read_backup(json)
        with self._storage.transaction() as store:
            root = _staff(req, store, ('root',))
            if store.users().count() > 1 and json.confirm != 'purge':
                raise falcon.HTTPConflict(code=PURGE_NEEDED, description='Everyone but root goes before the backup comes '
                                                                         "in; confirm with 'purge'")
            _check(backup, root, json.root_login)
            resp.media = restore_backup(store, backup, root.id, json.root_login)
            record(store, self._clock(), root.id, 'backup_restored', detail='root login' if json.root_login else '')
        if json.root_login:
            clear_session_cookie(resp)


def _check_two_factor(root: User, root_login: bool) -> None:
    """Without two-factor login, root only restores a backup whose root login it takes over (see may_restore_instead)."""
    if required(root) and not root.two_factor and not root_login:
        raise falcon.HTTPForbidden(description="Set up two-factor login first, on /2fa, or take over the backup's root login")


def _read_backup(json: RestoreInput) -> Backup:
    """The backup in the file; 422 if it cannot be read."""
    try:
        return read_backup_file(base64.b64decode(json.file, validate=True), json.passphrase)
    except (ValidationError, OSError, EOFError) as error:
        raise falcon.HTTPUnprocessableEntity(description='The backup file is damaged') from error
    except ValueError as error:
        raise falcon.HTTPUnprocessableEntity(description=str(error)) from error


def _check(backup: Backup, root: User, root_login: bool) -> None:
    try:
        check_backup(backup, root, root_login)
    except BackupError as error:
        raise falcon.HTTPUnprocessableEntity(description=str(error)) from error


class AdminAuditResource(_AdminResource):
    @spec.validate(resp=Response('HTTP_403', HTTP_200=list[AuditView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """The audit log, newest first (the latest 200): who changed whose role, team role or status, set a one-time
        password, switched registration or changed a team, and when."""
        with self._storage.transaction() as store:
            _staff(req, store)
            resp.media = [AuditView.of(entry) for entry in store.audit_log().latest()]


def _view(store: Store, user_id: str) -> AdminUserView:
    return AdminUserView.of(store.users().get(user_id), store.teams().membership(user_id))


def _team_view(store: Store, team_id: str) -> AdminTeamView:
    teams = store.teams()
    return AdminTeamView.of(teams.get(team_id), teams.members(team_id))
