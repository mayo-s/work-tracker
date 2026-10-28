"""OpenAPI documentation and request / response validation (spectree); docs at /apidoc/swagger."""

from spectree import SpecTree

spec = SpecTree(
    'falcon',
    title='Work Tracker API',
    description='Working days, task entries, overtime and PTO.',
    version='0.1.0',
    mode='strict',  # document only routes validated by this spec, not static files
)
