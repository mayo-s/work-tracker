"""Managed lists endpoints: /api/services and /api/activity-types (list, create, read, change, delete)."""

from typing import Any

import falcon
from pydantic import BaseModel, ConfigDict, Field
from spectree import Response

from src.models.catalog import ActivityType, Service
from src.modules.storage.catalog import ActivityTypeRepository, ServiceRepository
from src.modules.storage.database import Database
from src.utils.spec import spec


class ServiceInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    short_name: str = Field(min_length=1, max_length=30, examples=['MSB'])
    name: str = Field(default='', max_length=100, examples=['microsoft-bookings-service'])


class ActivityTypeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=50, examples=['Travel'])


def catalog_resources(repository: type, model: type[BaseModel], input_model: type[BaseModel], tag: str) -> tuple[Any, Any]:
    """Collection and item resources of one managed list.

    Names must be unique and records in use cannot be deleted (both 409).
    """
    tags = [tag]
    id_parameter = {'item_id': 'Id of the record'}

    class Collection:
        def __init__(self, database: Database) -> None:
            self._database = database

        @spec.validate(resp=Response(HTTP_200=list[model]), tags=tags)
        def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
            """All records of the list."""
            with self._database.transaction() as conn:
                resp.media = repository(conn).all()

        @spec.validate(json=input_model, resp=Response('HTTP_409', HTTP_201=model), tags=tags)
        def on_post(self, req: falcon.Request, resp: falcon.Response, json: input_model) -> None:
            """Add a record."""
            with self._database.transaction() as conn:
                added = repository(conn).add(model(**json.model_dump()))
            resp.status = falcon.HTTP_201
            resp.location = f'{req.path}/{added.id}'
            resp.media = added

    class Item:
        def __init__(self, database: Database) -> None:
            self._database = database

        @spec.validate(resp=Response('HTTP_404', HTTP_200=model), tags=tags, path_parameter_descriptions=id_parameter)
        def on_get(self, req: falcon.Request, resp: falcon.Response, item_id: int) -> None:
            """One record."""
            with self._database.transaction() as conn:
                resp.media = repository(conn).get(item_id)

        @spec.validate(json=input_model, resp=Response('HTTP_404', 'HTTP_409', HTTP_200=model), tags=tags,
                       path_parameter_descriptions=id_parameter)
        def on_put(self, req: falcon.Request, resp: falcon.Response, item_id: int, json: input_model) -> None:
            """Change a record."""
            with self._database.transaction() as conn:
                resp.media = repository(conn).update(model(id=item_id, **json.model_dump()))

        @spec.validate(resp=Response('HTTP_204', 'HTTP_404', 'HTTP_409'), tags=tags, path_parameter_descriptions=id_parameter)
        def on_delete(self, req: falcon.Request, resp: falcon.Response, item_id: int) -> None:
            """Delete a record."""
            with self._database.transaction() as conn:
                repository(conn).delete(item_id)
            resp.status = falcon.HTTP_204

    return Collection, Item


ServiceCollection, ServiceItem = catalog_resources(ServiceRepository, Service, ServiceInput, 'Services')
ActivityTypeCollection, ActivityTypeItem = catalog_resources(
    ActivityTypeRepository, ActivityType, ActivityTypeInput, 'Activity types'
)
