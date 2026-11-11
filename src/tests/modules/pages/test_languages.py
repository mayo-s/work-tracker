"""The UI languages (SPEC 5.16): which one a page gets, the catalogs, and translating the templates."""

import json
import re
from pathlib import Path

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.modules.pages.languages import LOCALES_DIR, accepted_language, html_texts, translate, translate_html
from src.modules.pages.resources import TEMPLATES_DIR

SOURCES = Path(__file__).resolve().parents[3]
PLACEHOLDER = re.compile(r'\{\w+\}')
QUOTED = r"'((?:[^'\\]|\\.)*)'"
COMMENTS = re.compile(r'/\*.*?\*/|(?:^|\s)//[^\n]*', re.DOTALL | re.MULTILINE)


@pytest.mark.parametrize('header, language', [
    ('de-AT,en;q=0.8', 'de'),
    ('fr-FR,es;q=0.5,en;q=0.6', 'en'),  # the most preferred of ours
    ('en;q=0,de;q=0.1', 'de'),  # q=0: not acceptable
    ('fr, it;q=oops', None),
    (None, None),
])
def test_the_browsers_language(header, language):
    assert accepted_language(header) == language


def test_translations_fill_in_their_placeholders_and_fall_back_to_english():
    assert [translate('{count} open team invitations', 'de', count=3), translate('Week', 'es'),
            translate('Week', 'en'), translate('Not in the catalog', 'de')] == [
        '3 offene Team-Einladungen', 'Semana', 'Week', 'Not in the catalog']


def test_templates_translate_texts_and_readable_attributes_but_not_names_and_placeholders():
    html = ('<a href="/" translate="no">Work Tracker</a>\n<nav aria-label="Main" class="Week">\n  <a href="/week">Week</a>'
            '\n</nav><title>{{title}} · Work Tracker</title><span aria-hidden="true">·</span>')
    assert translate_html(html, 'de') == (
        '<a href="/" translate="no">Work Tracker</a>\n<nav aria-label="Hauptnavigation" class="Week">\n'
        '  <a href="/week">Woche</a>\n</nav><title>{{title}} · Work Tracker</title><span aria-hidden="true">·</span>')


def page_language(client, path='/week', **headers):
    html = client.simulate_get(path, headers=headers).text
    return re.search(r'<html lang="(\w+)"', html)[1], re.search(r'<title>(.*)</title>', html)[1]


def test_a_page_comes_in_the_accounts_language_else_the_browsers_choice_else_its_language(client):
    assert page_language(client) == ('en', 'Week · Work Tracker')
    assert page_language(client, **{'Accept-Language': 'es-ES,es;q=0.9'}) == ('es', 'Semana · Work Tracker')
    assert page_language(client, **{'Accept-Language': 'es', 'Cookie': 'wt_language=de'}) == ('de', 'Woche · Work Tracker')
    saved = client.simulate_put('/api/language', json={'language': 'es'})
    cookie = saved.cookies['wt_language']
    assert (saved.json, cookie.value, cookie.http_only, cookie.same_site, cookie.max_age) == (
        {'language': 'es'}, 'es', True, 'Lax', 31536000)
    assert page_language(client, **{'Accept-Language': 'de', 'Cookie': 'wt_language=de'}) == ('es', 'Semana · Work Tracker')


def test_visitors_choose_too_kept_in_their_browser(database):
    app = testing.TestClient(create_app(database, auth=True))
    chosen = app.simulate_put('/api/language', json={'language': 'de'})
    assert (chosen.status, chosen.cookies['wt_language'].value) == (falcon.HTTP_200, 'de')
    assert page_language(app, '/login', Cookie='wt_language=de') == ('de', 'Anmelden · Work Tracker')


def test_only_our_languages(client):
    assert client.simulate_put('/api/language', json={'language': 'fr'}).status_code == 422


def texts_to_translate():
    """The frame's texts, the pages' titles and the scripts' texts (`t('…')`, `tn(count, '…', '…')`)."""
    texts = set(html_texts((TEMPLATES_DIR / 'frame.html').read_text(encoding='utf-8')))
    for source in (SOURCES / 'app.py', SOURCES / 'modules' / 'pages' / 'resources.py'):
        texts |= set(re.findall(rf"(?:Page\(|super\(\).__init__\()'[\w-]+', {QUOTED}", source.read_text(encoding='utf-8')))
    for script in (TEMPLATES_DIR / 'ts').glob('*.ts'):
        code = COMMENTS.sub('', script.read_text(encoding='utf-8'))
        texts |= set(re.findall(rf'(?<![\w.])t\(\s*{QUOTED}', code))
        texts |= {text for pair in re.findall(rf'(?<![\w.])tn\([^,]+,\s*{QUOTED},\s*{QUOTED}', code) for text in pair}
    return {text.replace("\\'", "'") for text in texts}


@pytest.mark.parametrize('language', ['de', 'es'])
def test_each_catalog_translates_every_text_with_its_placeholders_and_nothing_else(language):
    """A text added without its translations fails here; so does a translation no longer needed."""
    entries = json.loads((LOCALES_DIR / f'{language}.json').read_text(encoding='utf-8'))
    needed = texts_to_translate()
    placeholders = [text for text, translated in entries.items()
                    if set(PLACEHOLDER.findall(text)) != set(PLACEHOLDER.findall(translated))]
    assert (sorted(needed - set(entries)), sorted(set(entries) - needed), placeholders) == ([], [], [])
