"""The WSGI application: python -m src for a local server, or e.g. gunicorn 'src.app:create_app()'."""

import falcon

from src.defaultresources.default import Default
from src.modules.days.resources import DayCollection, DayItem
from src.modules.storage.database import Database, database_path
from src.modules.storage.errors import ConflictError, NotFoundError
from src.utils.spec import spec


def create_app(database: Database | None = None) -> falcon.App:
    """The app on the given database (default: $WORK_TRACKER_DB or work_tracker.db), migrated on start."""
    database = database or Database(database_path())
    database.migrate()
    app = falcon.App()
    app.add_error_handler(NotFoundError, _not_found)
    app.add_error_handler(ConflictError, _conflict)
    app.add_route('/', Default())
    app.add_route('/api/days', DayCollection(database))
    app.add_route('/api/days/{date:dt("%Y-%m-%d")}', DayItem(database))
    spec.register(app)
    return app


def _not_found(req: falcon.Request, resp: falcon.Response, error: NotFoundError, params: dict) -> None:
    raise falcon.HTTPNotFound(description=str(error))


def _conflict(req: falcon.Request, resp: falcon.Response, error: ConflictError, params: dict) -> None:
    raise falcon.HTTPConflict(description=str(error))
