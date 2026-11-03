"""Teams, their members (kept as history) and invitations; works within the transaction of the given connection."""

import datetime as dt
import sqlite3
from collections.abc import Callable

from src.models.base import new_id
from src.models.teams import Auditor, Invitation, Member, Membership, ReportView, Team, TeamRecord, TeamRole
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.store import Teams

_CURRENT = 'left_on IS NULL'


class TeamRepository:
    """Teams and who is in them. A user is in at most one team; joining another leaves the current one."""

    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], dt.datetime] | None = None) -> None:
        self._conn = conn
        self._clock = clock or dt.datetime.now

    def all(self) -> list[Team]:
        rows = self._conn.execute('SELECT id, name FROM teams WHERE deleted_at IS NULL ORDER BY name COLLATE NOCASE')
        return [Team(**dict(row)) for row in rows]

    def get(self, team_id: str) -> Team:
        row = self._conn.execute('SELECT id, name FROM teams WHERE id = ? AND deleted_at IS NULL', (team_id,)).fetchone()
        if row is None:
            raise NotFoundError(f'No team with id {team_id}')
        return Team(**dict(row))

    def add(self, team: Team) -> Team:
        added = team.model_copy(update={'id': new_id()})
        self._write('INSERT INTO teams (id, name) VALUES (?, ?)', (added.id, team.name), team.name)
        return added

    def rename(self, team: Team) -> Team:
        self.get(team.id)
        self._write('UPDATE teams SET name = ? WHERE id = ?', (team.name, team.id), team.name)
        return team

    def delete(self, team_id: str) -> None:
        """Only a team without members; its open invitations, services and auditors go with it, its history stays."""
        self.get(team_id)
        if self.members(team_id):
            raise ConflictError('The team still has members; remove them first')
        self._conn.execute('DELETE FROM team_invitations WHERE team_id = ?', (team_id,))
        self._conn.execute('DELETE FROM team_auditors WHERE team_id = ?', (team_id,))
        self._conn.execute('DELETE FROM services WHERE team_id = ?', (team_id,))
        self._conn.execute('UPDATE teams SET deleted_at = ? WHERE id = ?', (self._clock().isoformat(), team_id))

    def members(self, team_id: str) -> list[Member]:
        rows = self._conn.execute(
            'SELECT users.id AS user_id, username, email, first_name, last_name, team_role, joined_on FROM team_memberships'
            f' JOIN users ON users.id = user_id WHERE team_id = ? AND {_CURRENT} ORDER BY joined_on, username',
            (team_id,))
        return [Member(**dict(row)) for row in rows]

    def membership(self, user_id: str) -> Membership | None:
        """The user's current membership, if they are in a team."""
        history = [membership for membership in self.history(user_id) if membership.left_on is None]
        return history[0] if history else None

    def history(self, user_id: str) -> list[Membership]:
        """All teams the user was in, oldest first."""
        return self._memberships('user_id', user_id)

    def stays(self, team_id: str) -> list[Membership]:
        """Everyone who was ever in the team, each stay of theirs, oldest first."""
        return self._memberships('team_id', team_id)

    def with_deleted(self) -> list[TeamRecord]:
        """All teams, also the deleted ones, in the order they were created (for the full backup)."""
        return [TeamRecord(**dict(row)) for row in self._conn.execute('SELECT id, name, deleted_at FROM teams ORDER BY id')]

    def restore(self, team: TeamRecord) -> None:
        """A team of the full backup with its id, also a deleted one."""
        self._write('INSERT INTO teams (id, name, deleted_at) VALUES (?, ?, ?)',
                    (team.id, team.name, team.deleted_at.isoformat() if team.deleted_at else None), team.name)

    def restore_membership(self, membership: Membership) -> None:
        """A stay of the full backup, current or former, in the order they come."""
        self._conn.execute(
            'INSERT INTO team_memberships (id, team_id, user_id, joined_on, left_on, team_role) VALUES (?, ?, ?, ?, ?, ?)',
            (new_id(), membership.team_id, membership.user_id, membership.joined_on.isoformat(),
             membership.left_on.isoformat() if membership.left_on else None, membership.team_role))

    def _memberships(self, column: str, value: str) -> list[Membership]:
        rows = self._conn.execute(
            'SELECT team_id, teams.name AS team_name, user_id, joined_on, left_on, team_role FROM team_memberships'
            f' JOIN teams ON teams.id = team_id WHERE team_memberships.{column} = ? ORDER BY team_memberships.id', (value,))
        return [Membership(**dict(row)) for row in rows]

    def join(self, user_id: str, team_id: str) -> Membership:
        """The user joins the team today, leaving their current team first."""
        team = self.get(team_id)
        self.leave(user_id)
        today = self._clock().date()
        self._conn.execute('INSERT INTO team_memberships (id, team_id, user_id, joined_on) VALUES (?, ?, ?, ?)',
                           (new_id(), team_id, user_id, today.isoformat()))
        return Membership(team_id=team_id, team_name=team.name, user_id=user_id, joined_on=today)

    def leave(self, user_id: str) -> None:
        """The user leaves their team today: the team services their tickets use become personal services (an own
        service with the same short name is used instead of a copy); a team admin's role ends with the membership."""
        current = self.membership(user_id)
        if current is None:
            return
        for service_id, short_name, name in self._services_in_use(user_id, current.team_id):
            personal = self._personal_service(user_id, short_name, name)
            self._conn.execute('UPDATE tickets SET service_id = ? WHERE user_id = ? AND service_id = ?',
                               (personal, user_id, service_id))
        self._conn.execute(f'UPDATE team_memberships SET left_on = ? WHERE user_id = ? AND {_CURRENT}',
                           (self._clock().date().isoformat(), user_id))

    def set_team_role(self, user_id: str, team_role: TeamRole) -> Membership:
        """The role in the team the user is in now (409 if they are in none)."""
        if self.membership(user_id) is None:
            raise ConflictError('Only a member of a team has a team role; invite them first')
        self._conn.execute(f'UPDATE team_memberships SET team_role = ? WHERE user_id = ? AND {_CURRENT}',
                           (team_role, user_id))
        return self.membership(user_id)

    def _services_in_use(self, user_id: str, team_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            'SELECT DISTINCT services.id, short_name, name FROM services JOIN tickets ON tickets.service_id = services.id'
            ' WHERE tickets.user_id = ? AND services.team_id = ?', (user_id, team_id)).fetchall()

    def _personal_service(self, user_id: str, short_name: str, name: str) -> str:
        row = self._conn.execute('SELECT id FROM services WHERE user_id = ? AND short_name = ?',
                                 (user_id, short_name)).fetchone()
        if row:
            return row[0]
        service_id = new_id()
        self._conn.execute('INSERT INTO services (id, user_id, short_name, name) VALUES (?, ?, ?, ?)',
                           (service_id, user_id, short_name, name))
        return service_id

    def _write(self, sql: str, params: tuple, name: str) -> sqlite3.Cursor:
        try:
            return self._conn.execute(sql, params)
        except sqlite3.IntegrityError as error:
            raise ConflictError(f'A team named "{name}" already exists') from error


class AuditorRepository:
    """Who has the team view of which team read-only, and until when (SPEC 5.7); assigned by an admin."""

    _SELECT = ("SELECT team_id, user_id, until, assigned_by, assigned_at, teams.name AS team_name,"
               " trim(users.first_name || ' ' || users.last_name) AS user_name FROM team_auditors"
               ' JOIN teams ON teams.id = team_id JOIN users ON users.id = user_id')

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def assign(self, auditor: Auditor) -> None:
        """Assigns the user to the team, or changes the end date of an assignment."""
        self._conn.execute(
            'INSERT INTO team_auditors (team_id, user_id, until, assigned_by, assigned_at) VALUES (?, ?, ?, ?, ?)'
            ' ON CONFLICT (team_id, user_id) DO UPDATE SET until = excluded.until, assigned_by = excluded.assigned_by,'
            ' assigned_at = excluded.assigned_at',
            (auditor.team_id, auditor.user_id, auditor.until.isoformat() if auditor.until else None, auditor.assigned_by,
             auditor.assigned_at.isoformat()))

    def remove(self, team_id: str, user_id: str) -> None:
        if not self._conn.execute('DELETE FROM team_auditors WHERE team_id = ? AND user_id = ?', (team_id, user_id)).rowcount:
            raise NotFoundError('No such auditor')

    def all(self) -> list[Auditor]:
        return self._select('', ())

    def of_user(self, user_id: str) -> list[Auditor]:
        return self._select('WHERE user_id = ?', (user_id,))

    def of_team(self, team_id: str) -> list[Auditor]:
        return self._select('WHERE team_id = ?', (team_id,))

    def _select(self, where: str, params: tuple) -> list[Auditor]:
        rows = self._conn.execute(f'{self._SELECT} {where} ORDER BY teams.name COLLATE NOCASE, user_name', params)
        return [Auditor(**dict(row)) for row in rows]


class InvitationRepository:
    """Invitations to a team by e-mail address; the invited user accepts or declines them."""

    _SELECT = ('SELECT team_invitations.id, team_id, teams.name AS team_name, email, invited_by, invited_at'
               ' FROM team_invitations JOIN teams ON teams.id = team_id')

    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], dt.datetime] | None = None) -> None:
        self._conn = conn
        self._clock = clock or dt.datetime.now

    def invite(self, team_id: str, email: str, invited_by: str) -> None:
        """Invite whoever has this e-mail address (ignoring case); nothing tells whether such a user exists. Members
        of the team and users already invited are left as they are."""
        member = self._conn.execute(
            f'SELECT 1 FROM team_memberships JOIN users ON users.id = user_id WHERE team_id = ? AND {_CURRENT}'
            ' AND email = ?', (team_id, email.strip())).fetchone()
        if not member:
            self._conn.execute('INSERT INTO team_invitations (id, team_id, email, invited_by, invited_at)'
                               ' VALUES (?, ?, ?, ?, ?) ON CONFLICT (team_id, email) DO NOTHING',
                               (new_id(), team_id, email.strip(), invited_by, self._clock().isoformat()))

    def of_team(self, team_id: str) -> list[Invitation]:
        rows = self._conn.execute(f'{self._SELECT} WHERE team_id = ? ORDER BY invited_at, team_invitations.id', (team_id,))
        return [Invitation(**dict(row)) for row in rows]

    def withdraw(self, team_id: str, invitation_id: str) -> None:
        if not self._conn.execute('DELETE FROM team_invitations WHERE id = ? AND team_id = ?',
                                  (invitation_id, team_id)).rowcount:
            raise NotFoundError(f'No open invitation with id {invitation_id}')

    def of_user(self, user_id: str) -> list[Invitation]:
        """The open invitations to the user's e-mail address (of teams that still exist)."""
        rows = self._conn.execute(
            f'{self._SELECT} WHERE deleted_at IS NULL AND email = (SELECT email FROM users WHERE id = ?)'
            ' ORDER BY invited_at, team_invitations.id', (user_id,))
        return [Invitation(**dict(row)) for row in rows]

    def accept(self, user_id: str, invitation_id: str, teams: Teams) -> Membership:
        """The user joins the team (leaving their current one); their other invitations are declined."""
        invitation = self._own(user_id, invitation_id)
        membership = teams.join(user_id, invitation.team_id)
        self._conn.execute('DELETE FROM team_invitations WHERE email = ?', (invitation.email,))
        return membership

    def decline(self, user_id: str, invitation_id: str) -> None:
        self._conn.execute('DELETE FROM team_invitations WHERE id = ?', (self._own(user_id, invitation_id).id,))

    def all(self) -> list[Invitation]:
        """All open invitations, oldest first (for the full backup)."""
        rows = self._conn.execute(f'{self._SELECT} ORDER BY invited_at, team_invitations.id')
        return [Invitation(**dict(row)) for row in rows]

    def restore(self, invitation: Invitation) -> None:
        """An invitation of the full backup as it was."""
        self._conn.execute('INSERT INTO team_invitations (id, team_id, email, invited_by, invited_at) VALUES (?, ?, ?, ?, ?)',
                           (invitation.id, invitation.team_id, invitation.email, invitation.invited_by,
                            invitation.invited_at.isoformat()))

    def _own(self, user_id: str, invitation_id: str) -> Invitation:
        """One of the user's open invitations; another user's is unknown (404)."""
        for invitation in self.of_user(user_id):
            if invitation.id == invitation_id:
                return invitation
        raise NotFoundError(f'No open invitation with id {invitation_id}')


class ReportViewLog:
    """Which team admin looked at which report of a member, and when; the member sees it in their settings."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, view: ReportView) -> None:
        self._conn.execute('INSERT INTO report_views (id, member_id, viewer_id, report, period, viewed_at)'
                           ' VALUES (?, ?, ?, ?, ?, ?)',
                           (new_id(), view.member_id, view.viewer_id, view.report, view.period, view.viewed_at.isoformat()))

    def of_member(self, member_id: str, limit: int = 50) -> list[ReportView]:
        """The latest views of the member's reports, newest first."""
        rows = self._conn.execute(
            "SELECT member_id, viewer_id, trim(first_name || ' ' || last_name) AS viewer_name, report, period, viewed_at"
            ' FROM report_views JOIN users ON users.id = viewer_id WHERE member_id = ?'
            ' ORDER BY viewed_at DESC, report_views.id DESC LIMIT ?', (member_id, limit))
        return [ReportView(**dict(row)) for row in rows]

    def all(self) -> list[ReportView]:
        """All views of everyone's reports, oldest first (for the full backup)."""
        rows = self._conn.execute(
            "SELECT member_id, viewer_id, trim(first_name || ' ' || last_name) AS viewer_name, report, period, viewed_at"
            ' FROM report_views JOIN users ON users.id = viewer_id ORDER BY viewed_at, report_views.id')
        return [ReportView(**dict(row)) for row in rows]
