"""The WSGI application: python -m src for a local server, or e.g. gunicorn 'src.app:create_app()'."""

import datetime as dt
from collections.abc import Callable

import falcon

from src.defaultresources.default import Default
from src.modules.catalog.resources import ActivityTypeCollection, ActivityTypeItem, ServiceCollection, ServiceItem
from src.modules.days.resources import DayCollection, DayItem
from src.modules.entries.resources import EntryCollection, EntryHistory, EntryItem, EntrySplit
from src.modules.pages.resources import STATIC_DIR, Page, RevalidateStaticFiles
from src.modules.reports.resources import MonthReportResource, WeekReportResource, YearReportResource
from src.modules.review.resources import Review, ReviewFlagItem
from src.modules.storage.database import Database, database_path
from src.modules.storage.errors import ConflictError, NotFoundError
from src.modules.tickets.resources import TicketCollection, TicketItem, TicketRenaming, TicketServiceAssignment
from src.utils.spec import spec


def create_app(database: Database | None = None, today: Callable[[], dt.date] = dt.date.today) -> falcon.App:
    """The app on the given database (default: $WORK_TRACKER_DB or work_tracker.db), migrated on start.

    `today` decides up to which day reports count (replaceable for tests).
    """
    database = database or Database(database_path())
    database.migrate()
    app = falcon.App(middleware=[RevalidateStaticFiles()])
    app.add_error_handler(NotFoundError, _not_found)
    app.add_error_handler(ConflictError, _conflict)
    app.add_route('/', Page('week', 'Week'))
    app.add_route('/month', Page('month', 'Month'))
    app.add_route('/year', Page('year', 'Year'))
    app.add_route('/review', Page('review', 'Review'))
    app.add_route('/components', Page('components', 'Component gallery'))
    app.add_static_route('/static', STATIC_DIR)
    app.add_route('/health', Default())
    app.add_route('/api/days', DayCollection(database))
    app.add_route('/api/days/{date:dt("%Y-%m-%d")}', DayItem(database))
    app.add_route('/api/entries', EntryCollection(database))
    app.add_route('/api/entries/{entry_id:int}', EntryItem(database))
    app.add_route('/api/entries/{entry_id:int}/history', EntryHistory(database))
    app.add_route('/api/entries/{entry_id:int}/split', EntrySplit(database))
    app.add_route('/api/tickets', TicketCollection(database))
    app.add_route('/api/tickets/assign-service', TicketServiceAssignment(database))
    app.add_route('/api/tickets/{key}', TicketItem(database))
    app.add_route('/api/tickets/{key}/rename', TicketRenaming(database))
    app.add_route('/api/reports/weeks/{week}', WeekReportResource(database, today))
    app.add_route('/api/reports/months/{month:dt("%Y-%m")}', MonthReportResource(database, today))
    app.add_route('/api/reports/years/{year:int(4)}', YearReportResource(database, today))
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
