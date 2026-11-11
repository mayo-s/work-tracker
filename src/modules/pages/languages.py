"""The UI languages (SPEC 5.16): which one a request gets, and the catalogs that translate the English texts.

A catalog (`static/locales/<language>.json`, also loaded by the scripts) maps each English text to its translation;
placeholders such as `{username}` stay as they are. English needs none. A text without a translation shows in
English.
"""

import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated, get_args

import falcon
from falcon.app_helpers import default_serialize_error
from pydantic import PlainSerializer

from src.lib.texts import Text, fill, raised_text
from src.models.messages import SUPPORT
from src.models.users import DELETED_USER
from src.modules.auth.sessions import served_over_https
from src.modules.storage.store import Language

LANGUAGES: tuple[Language, ...] = get_args(Language)
SOURCE: Language = 'en'  # the language the texts are written in
LOCALES_DIR = Path(__file__).resolve().parents[2] / 'templates' / 'static' / 'locales'
COOKIE = 'wt_language'  # the choice of a browser, for the pages before the login
COOKIE_LIFETIME = 365 * 24 * 3600

# The HTML of the templates in tags and texts; the attributes whose values people read or hear
_TAGS = re.compile(r'(<[^>]*>)')
_ATTRIBUTES = re.compile(r'\b(aria-label|title|placeholder|alt)="([^"]*)"')
_LETTER = re.compile(r'[^\W\d_]')
_REQUEST_LANGUAGE: ContextVar[Language] = ContextVar('request_language', default=SOURCE)


def catalog(language: Language) -> dict[str, str]:
    """The translations into the language, read on each use (like the templates, so a change shows at once)."""
    if language == SOURCE:
        return {}
    return json.loads((LOCALES_DIR / f'{language}.json').read_text(encoding='utf-8'))


def translate(text: str, language: Language, **params: object) -> str:
    """The text in the language, its placeholders filled in, e.g. `translate('Deleted {username}', 'de', username=…)`."""
    return fill(catalog(language).get(text, text), params)


def translate_text(value: str, language: Language) -> str:
    """A text marked with `text()` in the language, else the value as it is."""
    if not isinstance(value, Text):
        return value
    params = {name: translate_text(param, language) if isinstance(param, str) else param
              for name, param in value.params.items()}
    return translate(value.template, language, **params)


def accepted_language(header: str | None) -> Language | None:
    """The browser's most preferred language of ours from its `Accept-Language`, e.g. `de` from `de-AT,en;q=0.8`."""
    return next((tag for tag in _preferred(header or '') if tag in LANGUAGES), None)


def _preferred(header: str) -> list[str]:
    """The languages of an `Accept-Language` header, most preferred first (by `q`, then in order), without regions and
    without those it refuses (`q=0`, or a `q` that is no number)."""
    ranked = []
    for position, item in enumerate(header.split(',')):
        tag, _, quality = item.strip().partition(';q=')
        weight = _weight(quality)
        if weight > 0:
            ranked.append((-weight, position, tag.split('-')[0].strip().lower()))
    return [tag for *_, tag in sorted(ranked)]


def _weight(quality: str) -> float:
    try:
        return float(quality) if quality else 1.0
    except ValueError:
        return 0.0


def chosen_language(req: falcon.Request, account: Language | None) -> Language:
    """The account's language, else the browser's choice (its cookie), else its own language, else English."""
    cookie = req.cookies.get(COOKIE)
    return (account or (cookie if cookie in LANGUAGES else None) or accepted_language(req.get_header('Accept-Language'))
            or SOURCE)


def set_language_cookie(req: falcon.Request, resp: falcon.Response, language: Language) -> None:
    resp.set_cookie(COOKIE, language, max_age=COOKIE_LIFETIME, path='/', secure=served_over_https(req), http_only=True,
                    same_site='Lax')


def _each_text(html: str, replace: Callable[[str], str]) -> str:
    """The HTML with each text and readable attribute value passed through `replace`, its whitespace collapsed.
    Unchanged: texts without letters, with a `{{placeholder}}`, or the text of an element marked `translate="no"`
    (one without elements inside)."""
    parts, untranslated = [], False
    for part in _TAGS.split(html):
        if part.startswith('<'):
            untranslated = 'translate="no"' in part
            parts.append(_ATTRIBUTES.sub(lambda match: f'{match[1]}="{_replaced(match[2], replace)}"', part))
        else:
            parts.append(part if untranslated else _replaced(part, replace))
    return ''.join(parts)


def _replaced(text: str, replace: Callable[[str], str]) -> str:
    core = ' '.join(text.split())
    if not _LETTER.search(core) or '{{' in core:
        return text
    before, after = text[:len(text) - len(text.lstrip())], text[len(text.rstrip()):]
    return before + replace(core) + after


def html_texts(html: str) -> list[str]:
    """The texts of the HTML that are translated, as the catalogs hold them."""
    found: list[str] = []
    _each_text(html, lambda text: found.append(text) or text)
    return found


def translate_html(html: str, language: Language) -> str:
    """The HTML with its texts in the language."""
    if language == SOURCE:
        return html
    entries = catalog(language)
    return _each_text(html, lambda text: entries.get(text, text))


class RequestLanguage:
    """Middleware: the language of the answer to an API request is the one of its `Accept-Language` (the scripts send
    the page's), else English."""

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        language = accepted_language(req.get_header('Accept-Language')) or SOURCE
        req.context.language_token = _REQUEST_LANGUAGE.set(language)

    def process_response(self, req: falcon.Request, resp: falcon.Response, resource: object, done: bool) -> None:
        if 'language_token' in req.context:
            _REQUEST_LANGUAGE.reset(req.context.language_token)


def request_language() -> Language:
    """The language of the request being answered (English outside of one)."""
    return _REQUEST_LANGUAGE.get()


@contextmanager
def answering_in(language: Language) -> Iterator[None]:
    """Within, the answer is in the language, whichever the request asks for (e.g. a CSV file, all English)."""
    token = _REQUEST_LANGUAGE.set(language)
    try:
        yield
    finally:
        _REQUEST_LANGUAGE.reset(token)


def serialize_error(req: falcon.Request, resp: falcon.Response, error: falcon.HTTPError) -> None:
    """Falcon's error answer, its description in the request's language."""
    if isinstance(error.description, Text):
        error.description = translate_text(error.description, request_language())
    default_serialize_error(req, resp, error)


def translate_validation_errors(resp: falcon.Response, error: Exception) -> None:
    """The messages of a refused request (422) in the request's language: those our validators raise as texts; pydantic's
    own stay English. `resp.media` holds the errors in the order of `error.errors()`."""
    language = request_language()
    for answered, detail in zip(resp.media, error.errors()):
        if raised := raised_text(detail):
            answered['msg'] = f'Value error, {translate_text(raised, language)}'


def in_request_language(value: str) -> str:
    """A text marked with `text()` in the language of the request being answered."""
    return translate_text(value, request_language())


def _translated_name(value: str) -> str:
    return translate(value, request_language())


def _person_name(value: str) -> str:
    return _translated_name(value) if value in (DELETED_USER, SUPPORT) else value


# The name of a public holiday or company half day, answered in the request's language
HolidayName = Annotated[str, PlainSerializer(_translated_name, return_type=str)]
# A person's name, or the name the app gives one that is gone (`Deleted user`, `Support`), answered in the request's language
PersonName = Annotated[str, PlainSerializer(_person_name, return_type=str)]
