import falcon
import pytest

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


def test_stylesheet(client):
    result = client.simulate_get('/static/css/main.css')
    assert result.status == falcon.HTTP_200
    assert result.headers['content-type'] == 'text/css'
    for color in ('#36454f', '#e62e6b', '#c81e57', '#1b7f61', '#2f6fd6', '#f4f7fb'):
        assert color in result.text


@pytest.mark.parametrize('font', ['Inter-Regular.woff2', 'Inter-SemiBold.woff2'])
def test_inter_font_is_served_from_the_project(client, font):
    result = client.simulate_get(f'/static/fonts/{font}')
    assert result.status == falcon.HTTP_200
    assert result.headers['content-type'] == 'font/woff2'
    assert result.content[:4] == b'wOF2'
    assert f"url('/static/fonts/{font}')" in client.simulate_get('/static/css/main.css').text


def test_inter_license_is_included():
    assert 'SIL Open Font License' in (STATIC_DIR / 'fonts' / 'Inter-LICENSE.txt').read_text()


def test_no_external_requests_in_frame_and_styles(client):
    for url in ('/', '/static/css/main.css'):
        assert 'http://' not in client.simulate_get(url).text.replace('http://www.w3.org', '')
        assert 'https://' not in client.simulate_get(url).text


def test_component_gallery_page(client):
    result = client.simulate_get('/components')
    assert result.status == falcon.HTTP_200
    assert '<title>Component gallery · Work Tracker</title>' in result.text
    assert 'data-page="components"' in result.text
    for story in ('colors', 'values', 'badges', 'buttons', 'forms', 'tables', 'entries', 'cards', 'navigation'):
        assert f'<section class="story" id="{story}">' in result.text


def test_gallery_is_not_in_the_main_navigation(client):
    assert '/components' not in client.simulate_get('/').text
