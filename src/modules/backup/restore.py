"""Restoring the full backup (SPEC 5.9): everything but root goes, then the backup comes in.

Root stays as it is: the backup's root is skipped, and what it did (audit log, assignments) is credited to the current
root. With `root_login`, the current root takes over the login of the backup's root instead (username, e-mail address,
name, password, two-factor login) and has to log in again. Everyone else gets their password and two-factor login from
the backup. Before anything is written, the backup
is checked to hold together. SQLite restores in the caller's transaction; DynamoDB writes atomic chunks and marks the
database until the restore finishes (a restore that stops halfway is completed by restoring again).
"""

from collections.abc import Callable, Iterable

from src.models.audit import AuditEntry
from src.models.catalog import Service, ServiceChoice
from src.models.users import User
from src.modules.backup.schemas import Backup, BackupTeam, BackupUser, RestoreSummary
from src.modules.storage.errors import ConflictError
from src.modules.storage.store import Store
from src.modules.userdata.importing import check_references, import_data

ROOM = 5  # the most items one record of the backup takes, e.g. a membership with its stay and member items
# Where the backup refers to users and teams: (list, field)
_USER_FIELDS = (('memberships', 'user_id'), ('auditors', 'user_id'), ('auditors', 'assigned_by'),
                ('invitations', 'invited_by'), ('report_views', 'member_id'), ('report_views', 'viewer_id'),
                ('audit_log', 'actor_id'), ('audit_log', 'user_id'), ('messages', 'user_id'), ('message_changes', 'actor_id'))
_TEAM_FIELDS = (('memberships', 'team_id'), ('auditors', 'team_id'), ('invitations', 'team_id'), ('audit_log', 'team_id'))


class BackupError(ValueError):
    """The backup does not hold together; nothing was written."""


def check_backup(backup: Backup, root: User, root_login: bool = False) -> None:
    """BackupError if the backup does not hold together: a reference to a user or team it does not hold, a username or
    e-mail address twice (also root's: the current one, or with `root_login` the backup's), or a ticket of a team service
    the user's team does not have."""
    people = _people(backup)
    _check_names(people, _root_of(backup).user if root_login else root)
    teams = {item.team.id: item for item in backup.teams}
    _known((item.user.id for item in backup.users), _references(backup, _USER_FIELDS), 'user')
    _known(teams, _references(backup, _TEAM_FIELDS), 'team')
    current = _current_teams(backup)
    for item in people:
        _check_records(item, teams.get(current.get(item.user.id)))


def _check_names(people: list[BackupUser], root: User) -> None:
    _unique([root.username, *(item.user.username for item in people)], 'username')
    _unique([root.email, *(item.user.email for item in people)], 'e-mail address')


def _check_records(item: BackupUser, team: BackupTeam | None) -> None:
    if item.records is None:
        raise BackupError(f'The backup holds no records of {item.user.username}')
    try:
        check_references(item.records)
    except ConflictError as error:
        raise BackupError(f'The records of {item.user.username}: {error}') from error
    for service in item.records.services:
        if service.team is not None and not _offered(service, team):
            raise BackupError(f'{item.user.username} uses the service {service.short_name} of {service.team}, which the '
                              'backup does not hold for their team')


def _offered(service: ServiceChoice, team: BackupTeam | None) -> bool:
    """Whether the team service is one of the user's team (a ticket can only have one of the own team)."""
    offered = {offer.short_name.casefold() for offer in team.services} if team else set()
    return team is not None and service.team == team.team.name and service.short_name.casefold() in offered


def restore_backup(store: Store, backup: Backup, root_id: str, root_login: bool = False) -> RestoreSummary:
    """Everything but root goes, then the backup (checked before, check_backup) comes in; with `root_login`, root takes
    over the login of the backup's root (its sessions end)."""
    store.start_restore()
    store.purge(root_id)
    if root_login:
        _take_over_root_login(store, _root_of(backup), root_id)
    store.set_registration(backup.registration)
    people = _people(backup)
    _users(store, people)
    team_services = _teams(store, backup)
    current = _current_teams(backup)
    for item in people:
        import_data(store, item.user.id, item.records, team_services.get(current.get(item.user.id), {}))
        if item.setup_done:
            store.finish_setup(item.user.id)
    _logs(store, backup, _as_current_root(backup, root_id))
    _messages(store, backup, _as_current_root(backup, root_id))
    store.finish_restore()
    return RestoreSummary(users=len(people), teams=len(backup.teams), audit_entries=len(backup.audit_log),
                          entries=sum(len(item.records.entries) for item in people))


def _as_current_root(backup: Backup, root_id: str) -> Callable[[str | None], str | None]:
    """A user id of the backup, with the backup's root as the current one."""
    root_of_backup = next((item.user.id for item in backup.users if item.user.role == 'root'), None)
    return lambda user_id: root_id if user_id is not None and user_id == root_of_backup else user_id


def _root_of(backup: Backup) -> BackupUser:
    root = next((item for item in backup.users if item.user.role == 'root'), None)
    if root is None:
        raise BackupError('The backup holds no root whose login could be taken over')
    return root


def _take_over_root_login(store: Store, root: BackupUser, root_id: str) -> None:
    """The current root keeps its id (and so what it did), and gets the login of the backup's root."""
    users = store.users()
    current = users.get(root_id)
    users.update(current.model_copy(update={field: getattr(root.user, field)
                                            for field in ('username', 'email', 'first_name', 'last_name')}))
    users.set_password_hash(root_id, root.password_hash)
    users.save_two_factor(root_id, root.two_factor)


def _users(store: Store, people: list[BackupUser]) -> None:
    users = store.users()
    for item in people:
        store.make_room(ROOM)
        users.restore(item.user, item.password_hash)
        if item.two_factor:
            users.save_two_factor(item.user.id, item.two_factor)


def _teams(store: Store, backup: Backup) -> dict[str, dict[str, str]]:
    """The teams with their services and stays; the new ids of the services by team and short name in lower case."""
    teams, services = store.teams(), {}
    for item in backup.teams:
        store.make_room(ROOM)
        teams.restore(item.team)
        repository = store.team_services(item.team.id)
        for service in item.services:
            store.make_room(ROOM)
            added = repository.add(Service(short_name=service.short_name, name=service.name))
            services.setdefault(item.team.id, {})[service.short_name.casefold()] = added.id
    for membership in backup.memberships:
        store.make_room(ROOM)
        teams.restore_membership(membership)
    return services


def _logs(store: Store, backup: Backup, person: Callable[[str | None], str | None]) -> None:
    """Invitations, auditors, the report view log and the audit log, with the backup's root as the current one."""
    invitations, auditors, views, log = store.invitations(), store.auditors(), store.report_views(), store.audit_log()
    for invitation in backup.invitations:
        store.make_room(ROOM)
        invitations.restore(invitation.model_copy(update={'invited_by': person(invitation.invited_by)}))
    for auditor in backup.auditors:
        store.make_room(ROOM)
        auditors.assign(auditor.model_copy(update={'assigned_by': person(auditor.assigned_by)}))
    for view in backup.report_views:
        store.make_room(ROOM)
        views.add(view.model_copy(update={'viewer_id': person(view.viewer_id)}))
    for entry in backup.audit_log:
        store.make_room(ROOM)
        log.add(AuditEntry(actor_id=person(entry.actor_id), action=entry.action, user_id=person(entry.user_id),
                           team_id=entry.team_id, detail=entry.detail, at=entry.at))


def _messages(store: Store, backup: Backup, person: Callable[[str | None], str | None]) -> None:
    """The messages of the contact page with their changes, with the backup's root as the current one."""
    messages = store.messages()
    for message in backup.messages:
        store.make_room(ROOM)
        messages.restore(message.model_copy(update={'user_id': person(message.user_id)}))
    for change in backup.message_changes:
        store.make_room(ROOM)
        messages.restore_change(change.model_copy(update={'actor_id': person(change.actor_id)}))


def _people(backup: Backup) -> list[BackupUser]:
    """Everyone in the backup but its root."""
    return [item for item in backup.users if item.user.role != 'root']


def _current_teams(backup: Backup) -> dict[str, str]:
    """The team each user is in now, by user id."""
    return {membership.user_id: membership.team_id for membership in backup.memberships if membership.left_on is None}


def _references(backup: Backup, fields: tuple[tuple[str, str], ...]) -> list[str | None]:
    return [getattr(record, field) for name, field in fields for record in getattr(backup, name)]


def _unique(values: list[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value.casefold() in seen:
            raise BackupError(f'The {label} {value} is in the backup twice, or is root\'s')
        seen.add(value.casefold())


def _known(held: Iterable[str], references: Iterable[str | None], label: str) -> None:
    ids = set(held)
    if missing := next((ref for ref in references if ref is not None and ref not in ids), None):
        raise BackupError(f'The backup refers to {label} {missing}, which it does not hold')
