"""The full backup (SPEC 5.9): the whole database as one document, version 1, for root.

It reuses the domain models and keeps the ids of users and teams, so memberships, auditors, invitations, the report
view log and the audit log refer to them. Each user's records are in the format of the export of the own data (SPEC
5.8, with file ids); a ticket's team service is one of the team the user is in, by its short name.
"""

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from src.models.audit import AuditEntry
from src.models.base import DomainModel
from src.models.catalog import Service
from src.models.teams import Auditor, Invitation, Membership, ReportView, TeamRecord
from src.models.users import PASSWORD_MIN_LENGTH, TwoFactor, User
from src.modules.userdata.schemas import UserData

FORMAT = 'work-tracker-backup'
VERSION = 1


class BackupUser(DomainModel):
    user: User
    password_hash: str
    two_factor: TwoFactor | None = None
    setup_done: bool
    records: UserData | None = Field(default=None, description='None for root, who tracks no work')


class BackupTeam(DomainModel):
    team: TeamRecord
    services: list[Service] = Field(description='The team services (none for a deleted team)')


class Backup(DomainModel):
    made_at: dt.datetime
    registration: bool
    users: list[BackupUser] = Field(description='In the order they registered, root among them')
    teams: list[BackupTeam] = Field(description='Also the deleted ones, which stay for the history')
    memberships: list[Membership] = Field(description="Every user's teams, past and present")
    invitations: list[Invitation]
    auditors: list[Auditor]
    report_views: list[ReportView]
    audit_log: list[AuditEntry] = Field(description='Oldest first')


class BackupInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    passphrase: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=200,
                            description=f'At least {PASSWORD_MIN_LENGTH} characters; stored nowhere: without it the file '
                                        'cannot be restored')


class RestoreInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    file: str = Field(min_length=1, description='The backup file, base64-encoded')
    passphrase: str = Field(min_length=1, max_length=200)
    confirm: str | None = Field(default=None, description="'purge' while anyone but root exists: everything but root "
                                                          'goes before the backup comes in')
    root_login: bool = Field(default=False, description="Take over the login of the backup's root (username, e-mail "
                                                        'address, name, password, two-factor login); root logs in again')


class RestoreSummary(BaseModel):
    users: int = Field(description='Restored users, without root')
    teams: int
    entries: int
    audit_entries: int
