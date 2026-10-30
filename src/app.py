"""The WSGI application: python -m src for a local server, or e.g. gunicorn 'src.app:create_app()'."""

import datetime as dt
from collections.abc import Callable

import falcon

from src.defaultresources.default import Default
from src.modules.admin.resources import (
    AdminSettingsResource, AdminTeamCollection, AdminTeamItem, AdminUserCollection, AdminUserItem,
)
from src.modules.auth.resources import (
    AuthStatusResource, FirstUserResource, LoginResource, LogoutResource, MeResource, PasswordResource, RegisterResource,
)
from src.modules.auth.sessions import Authentication, LocalUser, auth_enabled
from src.modules.catalog.resources import ActivityTypeCollection, ActivityTypeItem, ServiceCollection, ServiceItem
from src.modules.dashboard.resources import DashboardResource
from src.modules.days.resources import DayCollection, DayItem, DayRange
from src.modules.entries.resources import EntryCollection, EntryHistory, EntryItem, EntrySplit
from src.modules.pages.resources import (
    STATIC_DIR, Page, PageSettings, Redirect, RegisterPage, RevalidateStaticFiles, StartPage,
)
from src.modules.pto.resources import PtoYearCollection, PtoYearItem
from src.modules.reports.resources import MonthReportResource, WeekReportResource, YearReportResource
from src.modules.review.resources import Review, ReviewFlagItem
from src.modules.schedules.resources import ScheduleCollection, ScheduleItem
from src.modules.setup.resources import SetupImportResource, SetupResource
from src.modules.settings.resources import SettingsResource, ThemeResource
from src.modules.storage.database import Database
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.storage.sqlite import SqliteStorage
from src.modules.teams.resources import (
    MyInvitationAcceptance, MyInvitationItem, MyTeam, ServiceChoices, TeamInvitationItem, TeamInvitations, TeamItem,
    TeamMemberItem, TeamServiceCollection, TeamServiceItem,
)
from src.modules.tickets.resources import TicketCollection, TicketItem, TicketRenaming, TicketServiceAssignment
from src.modules.userdata.resources import ExportResource
from src.utils.spec import spec
from src.utils.stages import stage_storage


def create_app(
    database: Database | None = None, today: Callable[[], dt.date] = dt.date.today, auth: bool | None = None,
    clock: Callable[[], dt.datetime] = dt.datetime.now,
) -> falcon.App:
    """The app on the given database, or by default on the storage of the stage it runs in (stages.py), migrated
    on start; a wrong stage raises a StageError.

    `today` decides up to which day reports count, `clock` the time of sessions (both replaceable for tests).
    The login is on unless `auth` is False or, by default, WORK_TRACKER_AUTH=off.
    """
    storage = stage_storage() if database is None else SqliteStorage(database)
    storage.migrate()
    enabled = auth_enabled() if auth is None else auth
    login = [Authentication(storage, clock)] if enabled else [LocalUser(storage)]
    app = falcon.App(middleware=[*login, RevalidateStaticFiles(), PageSettings(storage)])
    app.add_error_handler(NotFoundError, _not_found)
    app.add_error_handler(ConflictError, _conflict)
    app.add_route('/', StartPage())
    app.add_route('/week', Page('week', 'Week'))
    app.add_route('/month', Page('month', 'Month'))
    app.add_route('/year', Page('year', 'Year'))
    app.add_route('/review', Page('review', 'Review'))
    app.add_route('/lists', Redirect('/settings#services'))
    app.add_route('/settings', Page('settings', 'Settings'))
    app.add_route('/setup', Page('setup', 'Setup'))
    app.add_route('/login', Page('login', 'Log in'))
    app.add_route('/register', RegisterPage(storage, enabled))
    app.add_route('/admin', Page('admin', 'Admin'))
    app.add_route('/team', Page('team', 'Team'))
    app.add_route('/components', Page('components', 'Component gallery'))
    app.add_static_route('/static', STATIC_DIR)
    app.add_route('/health', Default())
    app.add_route('/api/days', DayCollection(storage))
    app.add_route('/api/days/range', DayRange(storage))
    app.add_route('/api/days/{date:dt("%Y-%m-%d")}', DayItem(storage))
    app.add_route('/api/entries', EntryCollection(storage))
    app.add_route('/api/entries/{entry_id:int}', EntryItem(storage))
    app.add_route('/api/entries/{entry_id:int}/history', EntryHistory(storage))
    app.add_route('/api/entries/{entry_id:int}/split', EntrySplit(storage))
    app.add_route('/api/tickets', TicketCollection(storage))
    app.add_route('/api/tickets/assign-service', TicketServiceAssignment(storage))
    app.add_route('/api/tickets/{key}', TicketItem(storage))
    app.add_route('/api/tickets/{key}/rename', TicketRenaming(storage))
    app.add_route('/api/dashboard', DashboardResource(storage, today, clock))
    app.add_route('/api/reports/weeks/{week}', WeekReportResource(storage, today, clock))
    app.add_route('/api/reports/months/{month:dt("%Y-%m")}', MonthReportResource(storage, today, clock))
    app.add_route('/api/reports/years/{year:int(4)}', YearReportResource(storage, today, clock))
    app.add_route('/api/settings', SettingsResource(storage))
    app.add_route('/api/theme', ThemeResource(storage))
    app.add_route('/api/export', ExportResource(storage, clock))
    app.add_route('/api/setup', SetupResource(storage, clock))
    app.add_route('/api/setup/import', SetupImportResource(storage, clock))
    app.add_route('/api/auth/status', AuthStatusResource(storage, clock, enabled))
    app.add_route('/api/auth/login', LoginResource(storage, clock))
    app.add_route('/api/auth/logout', LogoutResource(storage, clock))
    app.add_route('/api/auth/first-user', FirstUserResource(storage, clock))
    app.add_route('/api/auth/register', RegisterResource(storage, clock, enabled))
    app.add_route('/api/auth/me', MeResource(storage, clock))
    app.add_route('/api/auth/me/password', PasswordResource(storage, clock))
    app.add_route('/api/admin/users', AdminUserCollection(storage))
    app.add_route('/api/admin/users/{user_id}', AdminUserItem(storage))
    app.add_route('/api/admin/settings', AdminSettingsResource(storage))
    app.add_route('/api/admin/teams', AdminTeamCollection(storage))
    app.add_route('/api/admin/teams/{team_id:int}', AdminTeamItem(storage, clock))
    app.add_route('/api/teams/{team_id:int}', TeamItem(storage, clock))
    app.add_route('/api/teams/{team_id:int}/invitations', TeamInvitations(storage, clock))
    app.add_route('/api/teams/{team_id:int}/invitations/{invitation_id:int}', TeamInvitationItem(storage, clock))
    app.add_route('/api/teams/{team_id:int}/members/{user_id}', TeamMemberItem(storage, clock))
    app.add_route('/api/teams/{team_id:int}/services', TeamServiceCollection(storage, clock))
    app.add_route('/api/teams/{team_id:int}/services/{service_id:int}', TeamServiceItem(storage, clock))
    app.add_route('/api/team', MyTeam(storage, clock))
    app.add_route('/api/team/invitations/{invitation_id:int}', MyInvitationItem(storage, clock))
    app.add_route('/api/team/invitations/{invitation_id:int}/accept', MyInvitationAcceptance(storage, clock))
    app.add_route('/api/work-schedules', ScheduleCollection(storage))
    app.add_route('/api/work-schedules/{schedule_id:int}', ScheduleItem(storage))
    app.add_route('/api/pto-years', PtoYearCollection(storage))
    app.add_route('/api/pto-years/{year:int(4)}', PtoYearItem(storage))
    app.add_route('/api/review', Review(storage))
    app.add_route('/api/review/flags/{flag_id:int}', ReviewFlagItem(storage))
    app.add_route('/api/services', ServiceCollection(storage))
    app.add_route('/api/service-choices', ServiceChoices(storage))
    app.add_route('/api/services/{item_id:int}', ServiceItem(storage))
    app.add_route('/api/activity-types', ActivityTypeCollection(storage))
    app.add_route('/api/activity-types/{item_id:int}', ActivityTypeItem(storage))
    spec.register(app)
    return app


def _not_found(req: falcon.Request, resp: falcon.Response, error: NotFoundError, params: dict) -> None:
    raise falcon.HTTPNotFound(description=str(error))


def _conflict(req: falcon.Request, resp: falcon.Response, error: ConflictError, params: dict) -> None:
    raise falcon.HTTPConflict(description=str(error))
