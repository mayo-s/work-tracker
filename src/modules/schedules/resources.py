"""Work schedule endpoints: /api/work-schedules and /api/work-schedules/{id} (list, add, read, change, delete)."""

import falcon
from spectree import Response

from src.modules.schedules.schemas import ScheduleInput, ScheduleView
from src.modules.storage.database import Database
from src.modules.storage.schedules import ScheduleRepository
from src.modules.auth.sessions import current_user
from src.utils.spec import spec

TAGS = ['Work schedules']
ID_PARAMETER = {'schedule_id': 'Id of the work schedule'}


class ScheduleCollection:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response(HTTP_200=list[ScheduleView]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """All work schedules, oldest first; each applies until the next one starts."""
        with self._database.transaction() as conn:
            resp.media = [ScheduleView.of(schedule) for schedule in ScheduleRepository(conn, current_user(req)).all()]

    @spec.validate(json=ScheduleInput, resp=Response('HTTP_409', HTTP_201=ScheduleView), tags=TAGS)
    def on_post(self, req: falcon.Request, resp: falcon.Response, json: ScheduleInput) -> None:
        """Add a work schedule; it applies from its start date until the next one starts."""
        with self._database.transaction() as conn:
            added = ScheduleRepository(conn, current_user(req)).add(json.to_schedule())
        resp.status = falcon.HTTP_201
        resp.location = f'{req.path}/{added.id}'
        resp.media = ScheduleView.of(added)


class ScheduleItem:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response('HTTP_404', HTTP_200=ScheduleView), tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, schedule_id: int) -> None:
        """One work schedule."""
        with self._database.transaction() as conn:
            resp.media = ScheduleView.of(ScheduleRepository(conn, current_user(req)).get(schedule_id))

    @spec.validate(json=ScheduleInput, resp=Response('HTTP_404', 'HTTP_409', HTTP_200=ScheduleView), tags=TAGS,
                   path_parameter_descriptions=ID_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, schedule_id: int, json: ScheduleInput) -> None:
        """Change a work schedule; the days it applies to are counted again."""
        with self._database.transaction() as conn:
            resp.media = ScheduleView.of(ScheduleRepository(conn, current_user(req)).update(json.to_schedule(schedule_id)))

    @spec.validate(resp=Response('HTTP_204', 'HTTP_404', 'HTTP_409'), tags=TAGS, path_parameter_descriptions=ID_PARAMETER)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, schedule_id: int) -> None:
        """Delete a work schedule (not the only one); its days then follow the schedule before it."""
        with self._database.transaction() as conn:
            ScheduleRepository(conn, current_user(req)).delete(schedule_id)
        resp.status = falcon.HTTP_204
