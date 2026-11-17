import json
import re

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.auth.schemas import AuthStatus, UserView
from src.modules.pages.resources import STATIC_DIR, TEMPLATES_DIR, StaticFiles, render_page
from src.tests.helpers import STATIC


def test_render_page_fills_the_frame():
    html = render_page('week', 'Week', '/static/v1')
    assert html.startswith('<!doctype html>')
    assert '<section id="week"' in html
    assert '{{' not in html


def test_the_login_status_in_a_page_neither_ends_its_script_nor_fills_a_placeholder():
    """It holds what users typed, e.g. their names."""
    klara = UserView(id='u1', username='klara', email='klara.himmel@example.com', first_name='</script>{{content}}',
                     last_name='Himmel & Co', role='user')
    login_status = AuthStatus(enabled=True, has_users=True, user=klara, registration=False)
    html = render_page('week', 'Week', '/static/v1', status=login_status)
    status = re.search(r'<script type="application/json" id="auth-status">(.*?)</script>', html)[1]
    assert json.loads(status)['user']['first_name'] == '</script>{{content}}'
    assert not re.search('[<>&]', status)


def test_every_page_links_imprint_privacy_contact_license_and_source_code_in_its_footer():
    footer = render_page('week', 'Week', '/static/v1').split('<footer class="app-footer">')[1]
    assert re.findall(r'<a href="([^"]+)"([^>]*)>([^<]+)', footer) == [  # GitHub in a new tab
        ('/imprint', '', 'Imprint'),
        ('/privacy', '', 'Privacy'),
        ('/contact', '', 'Contact'),
        ('https://github.com/mayo-s/work-tracker#license', ' target="_blank" rel="noopener"', 'License'),
        ('https://github.com/mayo-s/work-tracker', ' target="_blank" rel="noopener"', 'Source code')]
    assert footer.count('<span class="visually-hidden"> (opens in a new tab)</span>') == 2


def test_pages_load_the_frontend_under_the_static_files_version(client):
    """SPEC 7.4: the version changes with the files, so browsers may keep them."""
    paths = re.findall(r'(?:src|href)="(/static/[^"]+)"', client.simulate_get('/').text)
    assert [re.sub('^/static/[0-9a-f]{10}/', '', path) for path in paths] == ['favicon.svg', 'css/main.css', 'js/main.js']
    assert [client.simulate_get(path).status for path in paths] == [falcon.HTTP_200] * 3


def test_static_files(client):
    svg, css = client.simulate_get(f'{STATIC}/favicon.svg'), client.simulate_get(f'{STATIC}/css/main.css')
    assert (svg.status, svg.headers['content-type'], css.headers['content-type']) == (
        falcon.HTTP_200, 'image/svg+xml', 'text/css')


def test_static_files_only_under_their_version_and_no_refusal_is_kept(client):
    """A missing file, the former paths without version, another version: CloudFront must not keep the 404 a year."""
    answers = [client.simulate_get(path) for path in
               (f'{STATIC}/missing.css', '/static/css/main.css', '/static/0123456789/css/main.css')]
    assert [(answer.status, answer.headers['cache-control']) for answer in answers] == [(falcon.HTTP_404, 'no-store')] * 3


def test_static_route_stays_inside_the_static_folder(client):
    assert client.simulate_get(f'{STATIC}/../frame.html').status in (falcon.HTTP_400, falcon.HTTP_404)


def test_the_static_version_follows_the_files_locally_and_stays_on_lambda(tmp_path):
    (tmp_path / 'css').mkdir()
    (tmp_path / 'css' / 'main.css').write_text('a {}')
    local, on_lambda = StaticFiles(tmp_path), StaticFiles(tmp_path, fixed=True)
    before = local.version()
    (tmp_path / 'css' / 'main.css').write_text('b {}')
    changed = local.version()
    (tmp_path / 'css' / 'main.css').rename(tmp_path / 'css' / 'site.css')
    renamed = local.version()
    assert len({before, changed, renamed}) == 3
    assert on_lambda.version() == before
    (tmp_path / 'css' / 'site.css').rename(tmp_path / 'css' / 'main.css')
    (tmp_path / 'css' / 'main.css').write_text('a {}')
    assert local.version() == before


def test_pages_are_not_in_the_api_docs(client):
    paths = client.simulate_get('/apidoc/openapi.json').json['paths']
    assert '/' not in paths
    assert not any(path.startswith('/static') for path in paths)


@pytest.mark.parametrize('font', ['Inter-Regular.woff2', 'Inter-SemiBold.woff2'])
def test_inter_font_is_served_from_the_project(client, font):
    result = client.simulate_get(f'{STATIC}/fonts/{font}')
    assert result.status == falcon.HTTP_200
    assert result.headers['content-type'] == 'font/woff2'
    assert result.content[:4] == b'wOF2'
    assert f"url('../fonts/{font}')" in client.simulate_get(f'{STATIC}/css/main.css').text  # under the same version


def test_inter_license_is_included():
    assert 'SIL Open Font License' in (STATIC_DIR / 'fonts' / 'Inter-LICENSE.txt').read_text()


def test_no_external_requests_in_frame_and_styles(client):
    """Only links lead elsewhere (the footer's to GitHub); nothing a page loads comes from there."""
    html = client.simulate_get('/').text
    assert re.findall(r'<(\w+)[^>]*\b(?:src|href)="(?:https?:)?//', html) == ['a', 'a']
    css = client.simulate_get(f'{STATIC}/css/main.css').text
    assert 'http://' not in css.replace('http://www.w3.org', '')
    assert 'https://' not in css


def test_component_gallery_stories(client):
    html = client.simulate_get('/components').text
    for story in ('colors', 'values', 'badges', 'buttons', 'forms', 'tables', 'entries', 'cards', 'navigation'):
        assert f'<section class="story" id="{story}">' in html


def test_gallery_is_not_in_the_main_navigation(client):
    assert '/components' not in client.simulate_get('/').text


def test_static_files_are_rechecked_locally_and_kept_for_good_on_lambda(client, database):
    on_lambda = testing.TestClient(create_app(database, static_files=StaticFiles(fixed=True)))
    assert [app.simulate_get(f'{STATIC}/css/main.css').headers['cache-control'] for app in (client, on_lambda)] == [
        'no-cache', 'public, max-age=31536000, immutable']
    assert 'cache-control' not in client.simulate_get('/api/review').headers


SECURITY = {'strict-transport-security': 'max-age=31536000; includeSubDomains', 'x-content-type-options': 'nosniff',
            'referrer-policy': 'same-origin', 'content-security-policy': "frame-ancestors 'none'",
            'x-frame-options': 'DENY'}


def test_every_answer_carries_the_security_headers(client):
    """SPEC 7.4: HTTPS only after the first visit (HSTS), no sniffed content types, no address sent elsewhere, no
    frames."""
    answers = {path: client.simulate_get(path) for path in ('/week', '/api/review', f'{STATIC}/css/main.css', '/missing')}
    actual = {path: ({name: answer.headers.get(name) for name in SECURITY}, answer.status_code)
              for path, answer in answers.items()}
    assert actual == {'/week': (SECURITY, 200), '/api/review': (SECURITY, 200), f'{STATIC}/css/main.css': (SECURITY, 200),
                      '/missing': (SECURITY, 404)}


def test_main_navigation_links_all_pages(client):
    html = client.simulate_get('/').text
    assert '<a href="/">Dashboard</a>' in html
    assert '<a href="/week">Week</a>' in html
    assert '<a href="/month">Month</a>' in html
    assert '<a href="/year">Year</a>' in html
    assert '<a href="/review" hidden>Review</a>' in html  # shown while items are open
    assert '<a href="/settings">Settings</a>' in html


@pytest.mark.parametrize('path, page, title, element', [
    ('/', 'dashboard', 'Dashboard', 'id="dashboard"'),
    ('/week', 'week', 'Week', 'id="week"'),
    ('/month', 'month', 'Month', 'id="month"'),
    ('/year', 'year', 'Year', 'id="year"'),
    ('/review', 'review', 'Review', 'id="review-status"'),
    ('/settings', 'settings', 'Settings', 'id="settings-status"'),
    ('/components', 'components', 'Component gallery', 'class="story"'),
    ('/imprint', 'imprint', 'Imprint', 'id="imprint"'),
    ('/privacy', 'privacy', 'Privacy policy', 'id="privacy-controller"'),
    ('/contact', 'contact', 'Contact', 'id="contact"'),
    ('/support', 'support', 'Support', 'id="support"'),
])
def test_pages(client, path, page, title, element):
    result = client.simulate_get(path)
    assert result.status == falcon.HTTP_200
    assert result.headers['content-type'].startswith('text/html')
    assert f'<title>{title} · Work Tracker</title>' in result.text
    assert f'data-page="{page}"' in result.text
    assert element in result.text


def test_lists_forward_to_the_settings_page(client):
    result = client.simulate_get('/lists')
    assert result.status == falcon.HTTP_301
    assert result.headers['location'] == '/settings#services'


def test_skip_link_comes_first(client):
    html = client.simulate_get('/').text
    body = html[html.index('<body>'):]
    assert body.index('<a class="skip-link" href="#app">Skip to content</a>') < body.index('<header')
    assert '<main id="app" data-page="dashboard" tabindex="-1">' in html


def test_former_week_links_forward_to_the_week_page(client):
    result = client.simulate_get('/', query_string='week=2025-W49&edit=2025-12-06')
    assert (result.status, result.headers['location']) == (falcon.HTTP_301, '/week?week=2025-W49&edit=2025-12-06')


def test_imprint_and_privacy_policy_come_translated_with_a_link_to_the_binding_german_text(client):
    spanish = {'Accept-Language': 'es'}
    privacy = client.simulate_get('/privacy', headers=spanish).text
    german = client.simulate_get('/privacy', params={'lang': 'de'}, headers=spanish).text
    imprint = client.simulate_get('/imprint').text
    assert ('<div class="privacy" lang="es">' in privacy, 'href="/privacy?lang=de"' in privacy,
            '<div class="privacy" lang="de">' in german, '<title>Política de privacidad · Work Tracker</title>' in german,
            '<div class="imprint" lang="en">' in imprint) == (True, True, True, True, True)


def legal_outline(name):
    """The headings, paragraphs and list items of a legal text and the dates in it; of a translation without its note."""
    html = (TEMPLATES_DIR / 'pages' / f'{name}.html').read_text(encoding='utf-8')
    html = re.sub(r'<p class="muted">[^\n]*hreflang="de"[^\n]*</p>', '', html)
    return re.findall(r'<(h1|h2|p|ul|li|div)\b', html), re.findall(r'\d\d\.\d\d\.\d{4}', html)


@pytest.mark.parametrize('page', ['imprint', 'privacy'])
@pytest.mark.parametrize('language', ['en', 'es'])
def test_each_translation_of_a_legal_text_follows_the_german_one(page, language):
    """A change of the German text (a section, a paragraph, its date) fails here until the translations follow."""
    assert legal_outline(f'{page}.{language}') == legal_outline(page)
