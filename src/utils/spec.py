"""OpenAPI documentation and request / response validation (spectree); docs at /apidoc/swagger."""

import logging
from typing import Any

from spectree import SpecTree

MAINTENANCE = 'Maintenance'
logger = logging.getLogger(__name__)
_PAGE_TITLES = {'swagger': 'Swagger UI', 'redoc': 'ReDoc', 'scalar': 'Scalar'}


class WorkTrackerSpec(SpecTree):
    """Spectree, plus its own documentation routes listed under the Maintenance tag (spectree leaves them out)."""

    @property
    def spec(self) -> dict[str, Any]:
        document = super().spec
        for path, operation in self._documentation_routes().items():
            document['paths'].setdefault(path, {'get': operation})
        if MAINTENANCE not in [tag['name'] for tag in document.setdefault('tags', [])]:
            document['tags'].append({'name': MAINTENANCE})
        return document

    def _documentation_routes(self) -> dict[str, dict[str, Any]]:
        prefix = f'/{self.config.path}'
        routes = {f'{prefix}/{self.config.filename}': ('OpenAPI specification', 'application/json')}
        for page in self.config.page_templates:
            if page in _PAGE_TITLES:
                routes[f'{prefix}/{page}'] = (f'API documentation ({_PAGE_TITLES[page]})', 'text/html')
        return {path: _operation(path, summary, media_type) for path, (summary, media_type) in routes.items()}


def _operation(path: str, summary: str, media_type: str) -> dict[str, Any]:
    return {
        'summary': summary,
        'tags': [MAINTENANCE],
        'operationId': 'get' + path.replace('/', '_').replace('.', '_'),  # e.g. get_apidoc_openapi_json
        'responses': {'200': {'description': 'OK', 'content': {media_type: {}}}},
    }


def log_request_errors(req: Any, resp: Any, error: Exception | None, instance: Any, model_adapter: Any) -> None:
    """A request that fails validation (422) is logged with where it failed, not with its values: they may be personal
    data, e.g. a whole export file being imported."""
    if error:
        logger.error('422 Request Validation Error: %s', error_locations(model_adapter.validation_errors(error)))


def log_response_errors(req: Any, resp: Any, error: Exception | None, instance: Any, model_adapter: Any) -> None:
    """A response that fails validation (500) is logged like a request, without its values (e.g. an export)."""
    if error:
        logger.error('500 Response Validation Error: %s', error_locations(model_adapter.validation_errors(error)))


def error_locations(errors: list[dict[str, Any]]) -> str:
    """Each error as its location and type, e.g. `data.history.3.changed_at (datetime_parsing)`; never the input or the
    message, which may quote it (`Unknown federal state 'XX'`)."""
    return ', '.join(f'{".".join(map(str, error.get("loc", ())))} ({error.get("type", "error")})' for error in errors)


spec = WorkTrackerSpec(
    'falcon',
    title='Work Tracker API',
    description='Working days, task entries, overtime and PTO.',
    version='0.1.0',
    mode='strict',  # document only routes validated by this spec, not static files
    naming_strategy=lambda model: model.__name__,  # plain schema names (e.g. DayView) for the generated TypeScript types
    nested_naming_strategy=lambda _parent, child: child,  # shared nested schemas (e.g. DayType) instead of one per parent
    before=log_request_errors,
    after=log_response_errors,
)
