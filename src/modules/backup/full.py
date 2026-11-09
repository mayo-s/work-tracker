"""Making the full backup (SPEC 5.9) and its file: the whole database as JSON, gzip-compressed and encrypted with
root's passphrase. Not in it: sessions, remembered browsers, failed logins and the used setup tokens."""

import datetime as dt
import gzip

from src.lib.encryption import decrypt, encrypt, read_header
from src.models.users import User
from src.modules.backup.schemas import FORMAT, VERSION, Backup, BackupTeam, BackupUser
from src.modules.storage.store import Store
from src.modules.userdata.export import export_data


def make_backup(store: Store, made_at: dt.datetime) -> Backup:
    """Everything of every user and team, read in one transaction."""
    made_at = made_at.replace(microsecond=0)
    users = store.users().all()
    teams = store.teams()
    return Backup(
        made_at=made_at, registration=store.registration_open(), users=[_user(store, user, made_at) for user in users],
        teams=[BackupTeam(team=team, services=[] if team.deleted_at else store.team_services(team.id).all())
               for team in teams.with_deleted()],
        memberships=[membership for user in users for membership in teams.history(user.id)],
        invitations=store.invitations().all(), auditors=store.auditors().all(), report_views=store.report_views().all(),
        audit_log=store.audit_log().all(), messages=store.messages().all(), message_changes=store.messages().all_changes(),
    )


def _user(store: Store, user: User, made_at: dt.datetime) -> BackupUser:
    users = store.users()
    return BackupUser(user=user, password_hash=users.password_hash(user.id), two_factor=users.two_factor(user.id),
                      setup_done=store.setup_done(user.id),
                      records=None if user.role == 'root' else export_data(store, user.id, made_at))


def backup_file(backup: Backup, passphrase: str) -> bytes:
    """The file to download: a header line (format, version, how it is encrypted; nothing personal), then the backup
    as JSON, gzip-compressed and encrypted (AES-256-GCM, key from scrypt)."""
    plain = gzip.compress(backup.model_dump_json().encode(), mtime=0)
    return encrypt(plain, passphrase, {'format': FORMAT, 'version': VERSION})


def read_backup_file(content: bytes, passphrase: str) -> Backup:
    """The backup in the file; ValueError for another file or a newer version (checked first), DecryptionError for a
    wrong passphrase or a changed file, and ValueError or ValidationError for damaged contents."""
    header = read_header(content)
    if header.get('format') != FORMAT:
        raise ValueError('This is no Work Tracker backup')
    if not isinstance(header.get('version'), int) or header['version'] > VERSION:
        raise ValueError(f'The backup has version {header.get("version")}; this Work Tracker reads up to version {VERSION}')
    return Backup.model_validate_json(gzip.decompress(decrypt(content, passphrase)))
