"""The WSGI application: python -m src for a local server, or e.g. gunicorn 'src.app:create_app()'."""

import datetime as dt
from collections.abc import Callable

import falcon

from src.defaultresources.default import Default
from src.modules.admin.resources import (
    AdminAuditorCollection, AdminAuditorItem, AdminAuditResource, AdminBackupResource, AdminOneTimePassword,
    AdminRestoreResource, AdminSettingsResource, AdminTeamCollection, AdminTeamItem, AdminTwoFactorReset,
    AdminUserCollection, AdminUserItem,
)
from src.modules.auth.origin import OriginCheck, OriginSecret
from src.modules.auth.resources import (
    AuthStatusResource, LoginResource, LogoutResource, MeResource, MyAuditResource, NewAppResource, PasswordResource,
    RegisterResource, RecoveryCodesResource, RootResetResource, RootResource, TwoFactorOffResource, TwoFactorResource,
)
from src.modules.auth.sessions import Authentication, LocalUser, auth_enabled
from src.modules.auth.setup_token import SetupToken
from src.modules.catalog.resources import ActivityTypeCollection, ActivityTypeItem, ServiceCollection, ServiceItem
from src.modules.dashboard.resources import DashboardResource
from src.modules.days.resources import DayCollection, DayItem, DayRange
from src.modules.entries.resources import (
    EntryActivityTypeAssignment, EntryCollection, EntryHistory, EntryItem,
)
from src.modules.contact.resources import ContactResource
from src.modules.imprint.resources import ImprintResource
from src.modules.imprint.sources import EnvironmentImprint, ImprintSource
from src.modules.pages.resources import (
    STATIC_DIR, Page, PageSettings, Redirect, RegisterPage, RevalidateStaticFiles, StartPage,
)
from src.modules.pto.resources import PtoYearCollection, PtoYearItem
from src.modules.reports.resources import (
    MonthReportResource, TeamReportCsvResource, TeamReportResource, WeekReportResource, YearReportResource,
)
from src.modules.review.resources import Review, ReviewCountsResource
from src.modules.schedules.resources import ScheduleCollection, ScheduleItem
from src.modules.search.resources import SearchResource
from src.modules.setup.resources import SetupImportResource, SetupResource
from src.modules.settings.resources import SettingsResource, ThemeResource
from src.modules.storage.database import Database
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.sqlite import SqliteStorage
from src.modules.storage.store import Storage
from src.modules.support.resources import SupportMessageCollection, SupportMessageItem, SupportMessageNotes
from src.modules.teams.resources import (
    MyAudits, MyInvitationAcceptance, MyInvitationItem, MyTeam, ServiceChoices, TeamInvitationItem, TeamInvitations, TeamItem,
    TeamMemberItem, TeamServiceCollection, TeamServiceItem,
)
from src.modules.tickets.resources import TicketCollection, TicketItem, TicketRenaming, TicketServiceAssignment
from src.modules.userdata.resources import ExportResource
from src.utils.spec import spec
from src.utils.stages import stage_imprint, stage_origin_secret, stage_setup_token, stage_storage


def _middleware(
    storage: Storage, clock: Callable[[], dt.datetime], enabled: bool, origin_secret: OriginSecret | None,
) -> list[object]:
    """First the origin check (only with a secret), then the login (or the first user with the login off)."""
    origin = [OriginCheck(origin_secret)] if origin_secret else []
    login = [Authentication(storage, clock)] if enabled else [LocalUser(storage)]
    return [*origin, *login, RevalidateStaticFiles(), PageSettings(storage)]


def create_app(
    database: Database | None = None, today: Callable[[], dt.date] = dt.date.today, auth: bool | None = None,
    clock: Callable[[], dt.datetime] = dt.datetime.now, storage: Storage | None = None,
    setup_token: SetupToken | None = None, imprint: ImprintSource = EnvironmentImprint(),
    origin_secret: OriginSecret | None = None,
) -> falcon.App:
    """The app on the given storage or SQLite database, or by default on the storage of the stage it runs in
    (stages.py), migrated on start; a wrong stage raises a StageError.

    `today` decides up to which day reports count, `clock` the time of sessions (both replaceable for tests).
    Creating root needs `setup_token` if one is given, and by default the stage's (only on AWS Lambda).
    The imprint comes from `imprint`, by default from the stage's source, or $WORK_TRACKER_IMPRINT with a given storage.
    The login is on unless `auth` is False or, by default, WORK_TRACKER_AUTH=off. With `origin_secret` (by default the
    stage's, only on AWS Lambda), requests without it are refused: they did not come through the domain.
    """
    if storage is None and database is None:
        storage, setup_token, imprint = stage_storage(), stage_setup_token(), stage_imprint()
        origin_secret = stage_origin_secret()
    storage = storage or SqliteStorage(database)
    storage.migrate()
    enabled = auth_enabled() if auth is None else auth
    app = falcon.App(middleware=_middleware(storage, clock, enabled, origin_secret))
    app.add_error_handler(NotFoundError, _not_found)
    app.add_error_handler(ConflictError, _conflict)
    app.add_route('/', StartPage())
    app.add_route('/week', Page('week', 'Week'))
    app.add_route('/month', Page('month', 'Month'))
    app.add_route('/year', Page('year', 'Year'))
    app.add_route('/review', Page('review', 'Review'))
    app.add_route('/search', Page('search', 'Search'))
    app.add_route('/lists', Redirect('/settings#services'))
    app.add_route('/settings', Page('settings', 'Settings'))
    app.add_route('/setup', Page('setup', 'Setup'))
    app.add_route('/password', Page('password', 'New password'))
    app.add_route('/2fa', Page('two-factor', 'Two-factor login'))
    app.add_route('/login', Page('login', 'Log in'))
    app.add_route('/register', RegisterPage(storage, enabled))
    app.add_route('/admin', Page('admin', 'Admin'))
    app.add_route('/team', Page('team', 'Team'))
    app.add_route('/team/report', Page('team-report', 'Team report'))
    app.add_route('/components', Page('components', 'Component gallery'))
    app.add_route('/imprint', Page('imprint', 'Impressum'))
    app.add_route('/contact', Page('contact', 'Contact'))
    app.add_route('/support', Page('support', 'Support'))
    app.add_static_route('/static', STATIC_DIR)
    app.add_route('/health', Default())
    app.add_route('/api/imprint', ImprintResource(imprint))
    app.add_route('/api/contact', ContactResource(storage, clock))
    app.add_route('/api/support/messages', SupportMessageCollection(storage, clock))
    app.add_route('/api/support/messages/{message_id}', SupportMessageItem(storage, clock))
    app.add_route('/api/support/messages/{message_id}/notes', SupportMessageNotes(storage, clock))
    app.add_route('/api/days', DayCollection(storage))
    app.add_route('/api/days/range', DayRange(storage))
    app.add_route('/api/days/{date:dt("%Y-%m-%d")}', DayItem(storage))
    app.add_route('/api/entries', EntryCollection(storage))
    app.add_route('/api/entries/assign-activity-type', EntryActivityTypeAssignment(storage))
    app.add_route('/api/entries/{entry_id}', EntryItem(storage))
    app.add_route('/api/entries/{entry_id}/history', EntryHistory(storage))
    app.add_route('/api/tickets', TicketCollection(storage))
    app.add_route('/api/tickets/assign-service', TicketServiceAssignment(storage))
    app.add_route('/api/tickets/{key}', TicketItem(storage))
    app.add_route('/api/tickets/{key}/rename', TicketRenaming(storage))
    app.add_route('/api/dashboard', DashboardResource(storage, today, clock))
    app.add_route('/api/reports/weeks/{week}', WeekReportResource(storage, today, clock))
    app.add_route('/api/reports/months/{month:dt("%Y-%m")}', MonthReportResource(storage, today, clock))
    app.add_route('/api/reports/years/{year:int(4)}', YearReportResource(storage, today, clock))
    app.add_route('/api/search', SearchResource(storage))
    app.add_route('/api/settings', SettingsResource(storage))
    app.add_route('/api/theme', ThemeResource(storage))
    app.add_route('/api/export', ExportResource(storage, clock))
    app.add_route('/api/setup', SetupResource(storage))
    app.add_route('/api/setup/import', SetupImportResource(storage))
    app.add_route('/api/auth/status', AuthStatusResource(storage, clock, enabled, setup_token))
    app.add_route('/api/auth/login', LoginResource(storage, clock))
    app.add_route('/api/auth/logout', LogoutResource(storage, clock))
    app.add_route('/api/auth/root', RootResource(storage, clock, setup_token=setup_token))
    app.add_route('/api/auth/root/reset', RootResetResource(storage, clock, setup_token=setup_token))
    app.add_route('/api/auth/register', RegisterResource(storage, clock, enabled))
    app.add_route('/api/auth/me', MeResource(storage, clock))
    app.add_route('/api/auth/me/password', PasswordResource(storage, clock))
    app.add_route('/api/auth/me/audit', MyAuditResource(storage, clock))
    app.add_route('/api/auth/me/two-factor', TwoFactorResource(storage, clock))
    app.add_route('/api/auth/me/two-factor/off', TwoFactorOffResource(storage, clock))
    app.add_route('/api/auth/me/two-factor/recovery', RecoveryCodesResource(storage, clock))
    app.add_route('/api/auth/me/two-factor/new-app', NewAppResource(storage, clock))
    app.add_route('/api/admin/users', AdminUserCollection(storage, clock))
    app.add_route('/api/admin/users/{user_id}', AdminUserItem(storage, clock))
    app.add_route('/api/admin/users/{user_id}/one-time-password', AdminOneTimePassword(storage, clock))
    app.add_route('/api/admin/users/{user_id}/two-factor-reset', AdminTwoFactorReset(storage, clock))
    app.add_route('/api/admin/settings', AdminSettingsResource(storage, clock))
    app.add_route('/api/admin/backup', AdminBackupResource(storage, clock))
    app.add_route('/api/admin/restore', AdminRestoreResource(storage, clock))
    app.add_route('/api/admin/audit', AdminAuditResource(storage, clock))
    app.add_route('/api/admin/teams', AdminTeamCollection(storage, clock))
    app.add_route('/api/admin/teams/{team_id}', AdminTeamItem(storage, clock))
    app.add_route('/api/admin/auditors', AdminAuditorCollection(storage, clock))
    app.add_route('/api/admin/teams/{team_id}/auditors/{user_id}', AdminAuditorItem(storage, clock))
    app.add_route('/api/teams/{team_id}', TeamItem(storage, clock))
    app.add_route('/api/teams/{team_id}/invitations', TeamInvitations(storage, clock))
    app.add_route('/api/teams/{team_id}/invitations/{invitation_id}', TeamInvitationItem(storage, clock))
    app.add_route('/api/teams/{team_id}/members/{user_id}', TeamMemberItem(storage, clock))
    app.add_route('/api/teams/{team_id}/services', TeamServiceCollection(storage, clock))
    app.add_route('/api/teams/{team_id}/services/{service_id}', TeamServiceItem(storage, clock))
    app.add_route('/api/teams/{team_id}/report', TeamReportResource(storage, today, clock))
    app.add_route('/api/teams/{team_id}/report.csv', TeamReportCsvResource(storage, today, clock))
    app.add_route('/api/team', MyTeam(storage, clock))
    app.add_route('/api/audits', MyAudits(storage, clock))
    app.add_route('/api/team/invitations/{invitation_id}', MyInvitationItem(storage, clock))
    app.add_route('/api/team/invitations/{invitation_id}/accept', MyInvitationAcceptance(storage, clock))
    app.add_route('/api/work-schedules', ScheduleCollection(storage))
    app.add_route('/api/work-schedules/{schedule_id}', ScheduleItem(storage))
    app.add_route('/api/pto-years', PtoYearCollection(storage))
    app.add_route('/api/pto-years/{year:int(4)}', PtoYearItem(storage))
    app.add_route('/api/review', Review(storage, today))
    app.add_route('/api/review/counts', ReviewCountsResource(storage, today))
    app.add_route('/api/services', ServiceCollection(storage))
    app.add_route('/api/service-choices', ServiceChoices(storage))
    app.add_route('/api/services/{item_id}', ServiceItem(storage))
    app.add_route('/api/activity-types', ActivityTypeCollection(storage))
    app.add_route('/api/activity-types/{item_id}', ActivityTypeItem(storage))
    spec.register(app)
    return app


def _not_found(req: falcon.Request, resp: falcon.Response, error: NotFoundError, params: dict) -> None:
    raise falcon.HTTPNotFound(description=str(error))


def _conflict(req: falcon.Request, resp: falcon.Response, error: ConflictError, params: dict) -> None:
    raise falcon.HTTPConflict(description=str(error))
