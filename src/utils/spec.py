"""OpenAPI documentation and request / response validation (spectree); docs at /apidoc/swagger."""

from typing import Any

from spectree import SpecTree

MAINTENANCE = 'Maintenance'
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


spec = WorkTrackerSpec(
    'falcon',
    title='Work Tracker API',
    description='Working days, task entries, overtime and PTO.',
    version='0.1.0',
    mode='strict',  # document only routes validated by this spec, not static files
    naming_strategy=lambda model: model.__name__,  # plain schema names (e.g. DayView) for the generated TypeScript types
    nested_naming_strategy=lambda _parent, child: child,  # shared nested schemas (e.g. DayType) instead of one per parent
)
