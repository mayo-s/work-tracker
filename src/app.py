"""The WSGI application: python -m src for a local server, or e.g. gunicorn 'src.app:create_app()'."""

import datetime as dt
from collections.abc import Callable

import falcon

from src.defaultresources.default import Default
from src.modules.auth.resources import (
    AuthStatusResource, FirstUserResource, LoginResource, LogoutResource, MeResource, PasswordResource,
)
from src.modules.auth.sessions import Authentication, LocalUser, auth_enabled
from src.modules.catalog.resources import ActivityTypeCollection, ActivityTypeItem, ServiceCollection, ServiceItem
from src.modules.dashboard.resources import DashboardResource
from src.modules.days.resources import DayCollection, DayItem, DayRange
from src.modules.entries.resources import EntryCollection, EntryHistory, EntryItem, EntrySplit
from src.modules.pages.resources import STATIC_DIR, Page, PageSettings, Redirect, RevalidateStaticFiles, StartPage
from src.modules.pto.resources import PtoYearCollection, PtoYearItem
from src.modules.reports.resources import MonthReportResource, WeekReportResource, YearReportResource
from src.modules.review.resources import Review, ReviewFlagItem
from src.modules.schedules.resources import ScheduleCollection, ScheduleItem
from src.modules.setup.resources import SetupResource
from src.modules.settings.resources import SettingsResource, ThemeResource
from src.modules.storage.database import Database, database_path
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.tickets.resources import TicketCollection, TicketItem, TicketRenaming, TicketServiceAssignment
from src.utils.spec import spec


def create_app(
    database: Database | None = None, today: Callable[[], dt.date] = dt.date.today, auth: bool | None = None,
    clock: Callable[[], dt.datetime] = dt.datetime.now,
) -> falcon.App:
    """The app on the given database (default: $WORK_TRACKER_DB or work_tracker.db), migrated on start.

    `today` decides up to which day reports count, `clock` the time of sessions (both replaceable for tests).
    The login is on unless `auth` is False or, by default, WORK_TRACKER_AUTH=off.
    """
    database = database or Database(database_path())
    database.migrate()
    enabled = auth_enabled() if auth is None else auth
    login = [Authentication(database, clock)] if enabled else [LocalUser(database)]
    app = falcon.App(middleware=[*login, RevalidateStaticFiles(), PageSettings(database)])
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
    app.add_route('/components', Page('components', 'Component gallery'))
    app.add_static_route('/static', STATIC_DIR)
    app.add_route('/health', Default())
    app.add_route('/api/days', DayCollection(database))
    app.add_route('/api/days/range', DayRange(database))
    app.add_route('/api/days/{date:dt("%Y-%m-%d")}', DayItem(database))
    app.add_route('/api/entries', EntryCollection(database))
    app.add_route('/api/entries/{entry_id:int}', EntryItem(database))
    app.add_route('/api/entries/{entry_id:int}/history', EntryHistory(database))
    app.add_route('/api/entries/{entry_id:int}/split', EntrySplit(database))
    app.add_route('/api/tickets', TicketCollection(database))
    app.add_route('/api/tickets/assign-service', TicketServiceAssignment(database))
    app.add_route('/api/tickets/{key}', TicketItem(database))
    app.add_route('/api/tickets/{key}/rename', TicketRenaming(database))
    app.add_route('/api/dashboard', DashboardResource(database, today))
    app.add_route('/api/reports/weeks/{week}', WeekReportResource(database, today))
    app.add_route('/api/reports/months/{month:dt("%Y-%m")}', MonthReportResource(database, today))
    app.add_route('/api/reports/years/{year:int(4)}', YearReportResource(database, today))
    app.add_route('/api/settings', SettingsResource(database))
    app.add_route('/api/theme', ThemeResource(database))
    app.add_route('/api/setup', SetupResource(database, clock))
    app.add_route('/api/auth/status', AuthStatusResource(database, clock, enabled))
    app.add_route('/api/auth/login', LoginResource(database, clock))
    app.add_route('/api/auth/logout', LogoutResource(database, clock))
    app.add_route('/api/auth/first-user', FirstUserResource(database, clock))
    app.add_route('/api/auth/me', MeResource(database, clock))
    app.add_route('/api/auth/me/password', PasswordResource(database, clock))
    app.add_route('/api/work-schedules', ScheduleCollection(database))
    app.add_route('/api/work-schedules/{schedule_id:int}', ScheduleItem(database))
    app.add_route('/api/pto-years', PtoYearCollection(database))
    app.add_route('/api/pto-years/{year:int(4)}', PtoYearItem(database))
    app.add_route('/api/review', Review(database))
    app.add_route('/api/review/flags/{flag_id:int}', ReviewFlagItem(database))
    app.add_route('/api/services', ServiceCollection(database))
    app.add_route('/api/services/{item_id:int}', ServiceItem(database))
    app.add_route('/api/activity-types', ActivityTypeCollection(database))
    app.add_route('/api/activity-types/{item_id:int}', ActivityTypeItem(database))
    spec.register(app)
    return app


def _not_found(req: falcon.Request, resp: falcon.Response, error: NotFoundError, params: dict) -> None:
    raise falcon.HTTPNotFound(description=str(error))


def _conflict(req: falcon.Request, resp: falcon.Response, error: ConflictError, params: dict) -> None:
    raise falcon.HTTPConflict(description=str(error))
