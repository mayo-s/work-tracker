"""The UI languages (SPEC 5.16): which one a page gets, the catalogs, and translating the templates."""

import ast
import datetime as dt
import json
import re
from pathlib import Path

import falcon
import pytest
from falcon import testing
from pydantic import BaseModel

from src.app import create_app
from src.lib.public_holidays import STATES, HolidayRules, holidays_between
from src.lib.texts import joined, text
from src.models.messages import SUPPORT
from src.models.users import DELETED_USER
from src.modules.pages.languages import (
    LOCALES_DIR, PersonName, accepted_language, answering_in, html_texts, translate, translate_html, translate_text,
)
from src.modules.pages.resources import OWN_LANGUAGE, TEMPLATES_DIR

SOURCES = Path(__file__).resolve().parents[3]
PLACEHOLDER = re.compile(r'\{\w+\}')
QUOTED = r"'((?:[^'\\]|\\.)*)'"
LITERAL = r"""(?:'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")"""  # a string in single or double quotes
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


def test_marked_texts_translate_with_their_values_and_joined_ones_each_on_its_own():
    end = text('End {end} is before start {start}', end='08:00', start='09:00')
    both = joined([end, text('a break needs a start'), 'Field required'])
    assert (both, translate_text(both, 'de'), translate_text('Week', 'de')) == (
        'End 08:00 is before start 09:00; a break needs a start; Field required',
        'Ende 08:00 liegt vor Beginn 09:00; eine Pause braucht einen Beginn; Field required', 'Week')


def test_the_api_answers_refusals_validation_messages_and_holidays_in_the_requests_language(client):
    german = {'Accept-Language': 'de'}
    refused = client.simulate_get('/api/tickets/TNG-1', headers=german)
    invalid = client.simulate_put('/api/days/2026-11-02', json={'start': '09:00', 'end': '08:00'}, headers=german)
    christmas = client.simulate_get('/api/days', params={'week': '2026-W52'}, headers=german)
    assert (refused.json['description'], [error['msg'] for error in invalid.json],
            [day['holiday'] for day in christmas.json][3:6]) == (
        'Unbekanntes Ticket TNG-1', ['Value error, Ende 08:00 liegt vor Beginn 09:00'],
        ['Heiligabend', 'Erster Weihnachtstag', 'Zweiter Weihnachtstag'])


def test_names_the_app_gives_come_in_the_answers_language_but_peoples_names_stay():
    class Names(BaseModel):
        people: list[PersonName]

    with answering_in('es'):
        assert Names(people=[DELETED_USER, SUPPORT, 'Hans Dampf']).model_dump(mode='json') == {
            'people': ['Usuario eliminado', 'Soporte', 'Hans Dampf']}


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


def test_page_contents_come_in_the_language_but_not_those_of_pages_that_keep_their_own(client):
    german = {'Accept-Language': 'de'}
    week, search, gallery = (client.simulate_get(path, headers=german).text for path in ('/week', '/search', '/components'))
    assert ('>Freie Tage buchen</button>' in week, '<code translate="no">MSB</code>' in search,
            '<h1>Component gallery</h1>' in gallery, '>Einstellungen</a>' in gallery) == (True, True, True, True)


def test_visitors_choose_too_kept_in_their_browser(database):
    app = testing.TestClient(create_app(database, auth=True))
    chosen = app.simulate_put('/api/language', json={'language': 'de'})
    assert (chosen.status, chosen.cookies['wt_language'].value) == (falcon.HTTP_200, 'de')
    assert page_language(app, '/login', Cookie='wt_language=de') == ('de', 'Anmelden · Work Tracker')


def test_only_our_languages(client):
    assert client.simulate_put('/api/language', json={'language': 'fr'}).status_code == 422


def template_texts():
    """The texts of the frame and the pages, but of those that keep their own language (and their translations)."""
    pages = [page for page in (TEMPLATES_DIR / 'pages').glob('*.html') if page.name.split('.')[0] not in OWN_LANGUAGE]
    return {text for template in [TEMPLATES_DIR / 'frame.html', *pages]
            for text in html_texts(template.read_text(encoding='utf-8'))}


def page_titles():
    sources = [SOURCES / 'app.py', SOURCES / 'modules' / 'pages' / 'resources.py']
    return {title for source in sources
            for title in re.findall(rf"(?:Page\(|super\(\).__init__\()'[\w-]+', {QUOTED}", source.read_text(encoding='utf-8'))}


def scripts():
    """The code of each script without its comments."""
    return {script.name: COMMENTS.sub('', script.read_text(encoding='utf-8'))
            for script in (TEMPLATES_DIR / 'ts').glob('*.ts')}


def script_texts():
    """The texts of `t('…')` and `tn(count, '…', '…')` in the scripts."""
    literals = set()
    for code in scripts().values():
        literals.update(re.findall(rf'(?<![\w.])t\(\s*({LITERAL})', code))
        literals.update(*re.findall(rf'(?<![\w.])tn\([^,]+,\s*({LITERAL}),\s*({LITERAL})', code))
    return {literal[1:-1].replace("\\'", "'").replace('\\"', '"') for literal in literals}


def test_scripts_translate_whole_quoted_texts_only():
    """The catalogs' test reads texts in quotes: not in backticks (placeholders go into the parameters), not put together
    with `+` (the catalog would be asked for the whole, the test would find a part)."""
    unread = (rf'(?<![\w.])tn?\(\s*`|tn\([^,]+,\s*`|(?<![\w.])t\(\s*{LITERAL}\s*\+'
              rf'|(?<![\w.])tn\([^,]+,\s*{LITERAL}\s*\+|(?<![\w.])tn\([^,]+,\s*{LITERAL},\s*{LITERAL}\s*\+')
    assert [name for name, code in scripts().items() if re.search(unread, code)] == []


def text_calls():
    """The calls of `text(…)` in the server's code."""
    for source in SOURCES.rglob('*.py'):
        if 'tests' not in source.relative_to(SOURCES).parts:
            for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Call) and _called(node.func) == 'text':
                    yield source.name, node


def _called(func):
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None


def server_texts():
    return {call.args[0].value for _, call in text_calls() if call.args and _quoted(call.args[0])}


def test_the_server_marks_whole_texts_only():
    """The catalogs' test reads the texts of `text(…)`: a whole sentence in quotes, its values as parameters."""
    assert [name for name, call in text_calls() if len(call.args) != 1 or not _quoted(call.args[0])] == []


def _quoted(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def holiday_names():
    """The names of the public holidays of all federal states and of the company half days, this year and the next ten."""
    year = dt.date.today().year
    return {holiday.name for state in STATES
            for holiday in holidays_between(dt.date(year, 1, 1), dt.date(year + 10, 12, 31), HolidayRules(state))}


def texts_to_translate():
    return (template_texts() | page_titles() | script_texts() | server_texts() | holiday_names()
            | {DELETED_USER, SUPPORT})


@pytest.mark.parametrize('language', ['de', 'es'])
def test_each_catalog_translates_every_text_with_its_placeholders_and_nothing_else(language):
    """A text added without its translations fails here; so does a translation no longer needed."""
    entries = json.loads((LOCALES_DIR / f'{language}.json').read_text(encoding='utf-8'))
    needed = texts_to_translate()
    placeholders = [text for text, translated in entries.items()
                    if set(PLACEHOLDER.findall(text)) != set(PLACEHOLDER.findall(translated))]
    assert (sorted(needed - set(entries)), sorted(set(entries) - needed), placeholders) == ([], [], [])
