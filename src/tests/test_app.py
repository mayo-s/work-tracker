import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.storage.database import Database
from src.modules.storage.errors import ConflictError, NotFoundError


def test_default_resource_answers_in_plain_text(client):
    result = client.simulate_get('/health')
    assert result.status == falcon.HTTP_200
    assert result.headers['content-type'].startswith('text/plain')
    assert result.text == 'Work Tracker - All systems operational.'


def test_openapi_spec_documents_default_resource(client):
    paths = client.simulate_get('/apidoc/openapi.json').json['paths']
    assert '/health' in paths
    assert paths['/health']['get']['tags'] == ['Maintenance']
    assert '/' not in paths


def test_openapi_spec_lists_documentation_routes_under_maintenance(client):
    document = client.simulate_get('/apidoc/openapi.json').json
    documentation = {path: operations['get'] for path, operations in document['paths'].items() if path.startswith('/apidoc/')}
    assert set(documentation) == {'/apidoc/openapi.json', '/apidoc/swagger', '/apidoc/redoc', '/apidoc/scalar'}
    assert all(operation['tags'] == ['Maintenance'] for operation in documentation.values())
    assert documentation['/apidoc/swagger']['operationId'] == 'get_apidoc_swagger'
    assert [tag['name'] for tag in document['tags']].count('Maintenance') == 1


@pytest.mark.parametrize('page', ['swagger', 'redoc', 'scalar'])
def test_documentation_pages(client, page):
    assert client.simulate_get(f'/apidoc/{page}').status == falcon.HTTP_200


def test_app_migrates_the_database(tmp_path):
    database = Database(tmp_path / 'new.db')
    create_app(database)
    assert database.schema_version() > 0


class Failing:
    def __init__(self, error):
        self.error = error

    def on_get(self, req, resp):
        raise self.error


@pytest.mark.parametrize('error, status', [
    (NotFoundError('No entry with id 404'), falcon.HTTP_404),
    (ConflictError('2024 already holds data'), falcon.HTTP_409),
])
def test_storage_errors_become_http_errors(tmp_path, error, status):
    app = create_app(Database(tmp_path / 'app.db'))
    app.add_route('/failing', Failing(error))
    result = testing.TestClient(app).simulate_get('/failing')
    assert result.status == status
    assert result.json['description'] == str(error)
