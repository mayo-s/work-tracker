import re

import falcon
import pytest

from src.modules.pages.resources import STATIC_DIR, TEMPLATES_DIR, render_page


def test_render_page_fills_the_frame():
    html = render_page('week', 'Week')
    assert html.startswith('<!doctype html>')
    assert '<section id="week"' in html
    assert '{{' not in html


def test_every_page_links_imprint_privacy_contact_license_and_source_code_in_its_footer():
    footer = render_page('week', 'Week').split('<footer class="app-footer">')[1]
    assert re.findall(r'<a href="([^"]+)"([^>]*)>([^<]+)', footer) == [  # GitHub in a new tab
        ('/imprint', '', 'Imprint'),
        ('/privacy', '', 'Privacy'),
        ('/contact', '', 'Contact'),
        ('https://github.com/mayo-s/work-tracker#license', ' target="_blank" rel="noopener"', 'License'),
        ('https://github.com/mayo-s/work-tracker', ' target="_blank" rel="noopener"', 'Source code')]
    assert footer.count('<span class="visually-hidden"> (opens in a new tab)</span>') == 2


def test_pages_load_the_frontend(client):
    assert '<script type="module" src="/static/js/main.js"></script>' in client.simulate_get('/').text


def test_static_files(client):
    svg, css = client.simulate_get('/static/favicon.svg'), client.simulate_get('/static/css/main.css')
    assert (svg.status, svg.headers['content-type'], css.headers['content-type']) == (
        falcon.HTTP_200, 'image/svg+xml', 'text/css')


def test_missing_static_file(client):
    assert client.simulate_get('/static/missing.css').status == falcon.HTTP_404


def test_static_route_stays_inside_the_static_folder(client):
    assert client.simulate_get('/static/../frame.html').status in (falcon.HTTP_400, falcon.HTTP_404)


def test_pages_are_not_in_the_api_docs(client):
    paths = client.simulate_get('/apidoc/openapi.json').json['paths']
    assert '/' not in paths
    assert not any(path.startswith('/static') for path in paths)


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
    """Only links lead elsewhere (the footer's to GitHub); nothing a page loads comes from there."""
    html = client.simulate_get('/').text
    assert re.findall(r'<(\w+)[^>]*\b(?:src|href)="(?:https?:)?//', html) == ['a', 'a']
    css = client.simulate_get('/static/css/main.css').text
    assert 'http://' not in css.replace('http://www.w3.org', '')
    assert 'https://' not in css


def test_component_gallery_stories(client):
    html = client.simulate_get('/components').text
    for story in ('colors', 'values', 'badges', 'buttons', 'forms', 'tables', 'entries', 'cards', 'navigation'):
        assert f'<section class="story" id="{story}">' in html


def test_gallery_is_not_in_the_main_navigation(client):
    assert '/components' not in client.simulate_get('/').text


def test_static_files_are_revalidated(client):
    assert client.simulate_get('/static/css/main.css').headers['cache-control'] == 'no-cache'
    assert 'cache-control' not in client.simulate_get('/api/review').headers


SECURITY = {'strict-transport-security': 'max-age=31536000; includeSubDomains', 'x-content-type-options': 'nosniff',
            'referrer-policy': 'same-origin', 'content-security-policy': "frame-ancestors 'none'",
            'x-frame-options': 'DENY'}


def test_every_answer_carries_the_security_headers(client):
    """SPEC 7.4: HTTPS only after the first visit (HSTS), no sniffed content types, no address sent elsewhere, no
    frames."""
    answers = {path: client.simulate_get(path) for path in ('/week', '/api/review', '/static/css/main.css', '/missing')}
    actual = {path: ({name: answer.headers.get(name) for name in SECURITY}, answer.status_code)
              for path, answer in answers.items()}
    assert actual == {'/week': (SECURITY, 200), '/api/review': (SECURITY, 200), '/static/css/main.css': (SECURITY, 200),
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
