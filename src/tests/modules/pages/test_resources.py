import falcon

from src.modules.pages.resources import STATIC_DIR, TEMPLATES_DIR, render_page


def test_templates_dir():
    assert (TEMPLATES_DIR / 'frame.html').is_file()
    assert STATIC_DIR == TEMPLATES_DIR / 'static'


def test_render_page_fills_the_frame():
    html = render_page('week', 'Week')
    assert html.startswith('<!doctype html>')
    assert '<title>Week · Work Tracker</title>' in html
    assert '<main id="app" data-page="week">' in html
    assert '<section id="week"' in html
    assert '{{' not in html


def test_week_page_at_root(client):
    result = client.simulate_get('/')
    assert result.status == falcon.HTTP_200
    assert result.headers['content-type'].startswith('text/html')
    assert '<script type="module" src="/static/js/main.js"></script>' in result.text
    assert 'data-page="week"' in result.text


def test_static_files(client):
    result = client.simulate_get('/static/favicon.svg')
    assert result.status == falcon.HTTP_200
    assert result.headers['content-type'] == 'image/svg+xml'


def test_missing_static_file(client):
    assert client.simulate_get('/static/missing.css').status == falcon.HTTP_404


def test_static_route_stays_inside_the_static_folder(client):
    assert client.simulate_get('/static/../frame.html').status in (falcon.HTTP_400, falcon.HTTP_404)


def test_pages_are_not_in_the_api_docs(client):
    paths = client.simulate_get('/apidoc/openapi.json').json['paths']
    assert '/' not in paths
    assert not any(path.startswith('/static') for path in paths)
