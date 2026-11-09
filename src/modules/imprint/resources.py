"""Imprint endpoint: /api/imprint, open to everyone like the page /imprint (SPEC 5.13)."""

import logging

import falcon
from pydantic import ValidationError
from spectree import Response

from src.modules.imprint.schemas import ImprintDetails
from src.modules.imprint.sources import ImprintSource
from src.utils.spec import error_locations, spec

TAGS = ['Imprint']
NOT_CONFIGURED = 'The imprint is not configured'
logger = logging.getLogger(__name__)


class ImprintResource:
    def __init__(self, source: ImprintSource) -> None:
        self._source = source

    @spec.validate(resp=Response('HTTP_404', HTTP_200=ImprintDetails), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Who runs the app, as German law requires (§ 5 DDG): name, postal address and e-mail address; 404 while they
        are not configured."""
        resp.media = imprint_details(self._source)


def imprint_details(source: ImprintSource) -> ImprintDetails:
    """The details of the source; missing or broken ones are logged by where they fail, never with their values."""
    value = source.read()
    if value is None:
        logger.error('%s: no imprint in %s', NOT_CONFIGURED, source.where)
        raise falcon.HTTPNotFound(description=NOT_CONFIGURED)
    try:
        return ImprintDetails.model_validate_json(value)
    except ValidationError as error:
        logger.error('%s: %s in %s', NOT_CONFIGURED, error_locations(error.errors()), source.where)
        raise falcon.HTTPNotFound(description=NOT_CONFIGURED) from error
