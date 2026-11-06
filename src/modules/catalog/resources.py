"""Managed lists endpoints: /api/services and /api/activity-types (list, create, read, change, delete)."""

from collections.abc import Callable
from typing import Any

import falcon
from pydantic import BaseModel, ConfigDict, Field
from spectree import Response

from src.models.catalog import ActivityType, Service
from src.modules.auth.sessions import current_user
from src.modules.storage.store import Catalog, Storage, Store
from src.utils.spec import spec


class ServiceInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    short_name: str = Field(min_length=1, max_length=30, examples=['MSB'])
    name: str = Field(default='', max_length=100, examples=['microsoft-bookings-service'])


class ActivityTypeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=50, examples=['Travel'])
    ticket_required: bool = Field(default=False, description='An entry of this type needs a ticket, e.g. Coding')


def catalog_resources(
    repository: Callable[[Store, str], Catalog], model: type[BaseModel], input_model: type[BaseModel], tag: str,
) -> tuple[Any, Any]:
    """Collection and item resources of one managed list; `repository` gets it from the store for a user.

    Names must be unique and records in use cannot be deleted (both 409).
    """
    tags = [tag]
    id_parameter = {'item_id': 'Id of the record'}

    class Collection:
        def __init__(self, storage: Storage) -> None:
            self._storage = storage

        @spec.validate(resp=Response(HTTP_200=list[model]), tags=tags)
        def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
            """All records of the list."""
            with self._storage.transaction() as store:
                resp.media = repository(store, current_user(req)).all()

        @spec.validate(json=input_model, resp=Response('HTTP_409', HTTP_201=model), tags=tags)
        def on_post(self, req: falcon.Request, resp: falcon.Response, json: input_model) -> None:
            """Add a record."""
            with self._storage.transaction() as store:
                added = repository(store, current_user(req)).add(model(**json.model_dump()))
            resp.status = falcon.HTTP_201
            resp.location = f'{req.path}/{added.id}'
            resp.media = added

    class Item:
        def __init__(self, storage: Storage) -> None:
            self._storage = storage

        @spec.validate(resp=Response('HTTP_404', HTTP_200=model), tags=tags, path_parameter_descriptions=id_parameter)
        def on_get(self, req: falcon.Request, resp: falcon.Response, item_id: str) -> None:
            """One record."""
            with self._storage.transaction() as store:
                resp.media = repository(store, current_user(req)).get(item_id)

        @spec.validate(json=input_model, resp=Response('HTTP_404', 'HTTP_409', HTTP_200=model), tags=tags,
                       path_parameter_descriptions=id_parameter)
        def on_put(self, req: falcon.Request, resp: falcon.Response, item_id: str, json: input_model) -> None:
            """Change a record."""
            with self._storage.transaction() as store:
                resp.media = repository(store, current_user(req)).update(model(id=item_id, **json.model_dump()))

        @spec.validate(resp=Response('HTTP_204', 'HTTP_404', 'HTTP_409'), tags=tags, path_parameter_descriptions=id_parameter)
        def on_delete(self, req: falcon.Request, resp: falcon.Response, item_id: str) -> None:
            """Delete a record."""
            with self._storage.transaction() as store:
                repository(store, current_user(req)).delete(item_id)
            resp.status = falcon.HTTP_204

    return Collection, Item


ServiceCollection, ServiceItem = catalog_resources(
    lambda store, user_id: store.services(user_id), Service, ServiceInput, 'Services'
)
ActivityTypeCollection, ActivityTypeItem = catalog_resources(
    lambda store, user_id: store.activity_types(user_id), ActivityType, ActivityTypeInput, 'Activity types'
)
