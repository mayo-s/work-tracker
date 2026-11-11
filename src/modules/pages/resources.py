"""Frontend pages: the shared frame (src/templates/frame.html) around a page's content (src/templates/pages)."""

from pathlib import Path

import falcon

from src.modules.pages.languages import LANGUAGES, chosen_language, translate, translate_html
from src.modules.storage.owners import NO_OWNER
from src.modules.storage.store import Language, Storage, Store, Theme

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / 'templates'
STATIC_DIR = TEMPLATES_DIR / 'static'
# the setup does not wait for them: the first two come first
BEFORE_SETUP = ('password', 'two-factor', 'imprint', 'privacy', 'contact')
# Pages whose content keeps its language (SPEC 5.16): the component gallery, a reference for developers, in English;
# imprint and privacy policy, German legal texts translated as a whole (e.g. `privacy.en.html`), the German binding
OWN_LANGUAGE = ('components', 'imprint', 'privacy')


def render_page(name: str, title: str, theme: str = 'system', language: Language = 'en',
                content_language: Language | None = None) -> str:
    """The frame with the page's title, name, content and color theme filled in (`system` sets no theme), in the
    language. The pages that keep their own (OWN_LANGUAGE) come as they are, in their translation into the content
    language (by default the page's) if there is one."""
    frame = translate_html((TEMPLATES_DIR / 'frame.html').read_text(encoding='utf-8'), language)
    if name in OWN_LANGUAGE:
        content = _own_content(name, content_language or language)
    else:
        content = translate_html(_content(name), language)
    theme_attribute = '' if theme == 'system' else f' data-theme="{theme}"'
    return (frame.replace('{{language}}', language).replace('{{title}}', translate(title, language))
            .replace('{{page}}', name).replace('{{theme}}', theme_attribute).replace('{{content}}', content))


def _content(name: str) -> str:
    return (TEMPLATES_DIR / 'pages' / f'{name}.html').read_text(encoding='utf-8').rstrip('\n')


def _own_content(name: str, language: Language) -> str:
    translated = f'{name}.{language}'
    return _content(translated if (TEMPLATES_DIR / 'pages' / f'{translated}.html').exists() else name)


class Page:
    """Serves one page; files are read on each request, so template changes show without a restart."""

    def __init__(self, name: str, title: str) -> None:
        self.name = name
        self._title = title

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """`?lang=de` shows the content of imprint and privacy policy in German (the binding text) whatever the page's
        language."""
        resp.content_type = falcon.MEDIA_HTML
        content_language = req.get_param('lang')
        resp.text = render_page(self.name, self._title, req.context.get('theme', 'system'), req.context.get('language', 'en'),
                                content_language if content_language in LANGUAGES else None)


class StartPage(Page):
    """The dashboard at `/`; former week view links (`/?week=…`, `&edit=…`, `&entry=…`) forward to `/week`."""

    def __init__(self) -> None:
        super().__init__('dashboard', 'Dashboard')

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        if {'week', 'edit', 'entry'} & set(req.params):
            raise falcon.HTTPMovedPermanently(f'/week?{req.query_string}')
        super().on_get(req, resp)


class RegisterPage(Page):
    """`/register`, only while registration is on (and the login, since only then are there users to register)."""

    def __init__(self, storage: Storage, enabled: bool) -> None:
        super().__init__('register', 'Register')
        self._storage = storage
        self._enabled = enabled

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        with self._storage.transaction() as store:
            if not (self._enabled and store.registration_open()):
                raise falcon.HTTPNotFound(description='Registration is switched off')
        super().on_get(req, resp)


class PageSettings:
    """Middleware for pages: the color theme and the language (SPEC 5.16); until the database is set up, pages forward
    to /setup, and /setup forwards to the week once it is. The imprint, the privacy policy and the contact page are
    always there (SPEC 5.13–5.15)."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def process_resource(self, req: falcon.Request, resp: falcon.Response, resource: object, params: dict) -> None:
        if not isinstance(resource, Page):
            return
        user_id = req.context.get('user_id')
        with self._storage.transaction() as store:
            done = _set_up(store, user_id)
            req.context.theme, account = _appearance(store, user_id)
        req.context.language = chosen_language(req, account)
        if resource.name not in BEFORE_SETUP and done == (resource.name == 'setup'):
            raise falcon.HTTPSeeOther('/' if done else '/setup')


def _appearance(store: Store, user_id: str | None) -> tuple[Theme, Language | None]:
    """The user's color theme and chosen language; not logged in, the theme of the data without owner and no language
    (the browser's applies)."""
    if user_id is None:
        return store.load_theme(NO_OWNER), None
    return store.load_theme(user_id), store.load_language(user_id)


def _set_up(store: Store, user_id: str | None) -> bool:
    """The user's setup state (root has none to do); not logged in, only a database without users is set up first,
    creating root (the login handles the rest)."""
    if user_id is not None:
        return store.users().root_id() == user_id or store.setup_done(user_id)
    return bool(store.users().count()) or store.setup_done(NO_OWNER)


class Redirect:
    """Forwards a former page address, e.g. /lists to /settings#services."""

    def __init__(self, location: str) -> None:
        self._location = location

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        raise falcon.HTTPMovedPermanently(self._location)


SECURITY_HEADERS = {
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',  # browsers ignore it over plain HTTP
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'same-origin',
    'Content-Security-Policy': "frame-ancestors 'none'",
    'X-Frame-Options': 'DENY',  # frame-ancestors for older browsers
}


class SecurityHeaders:
    """Middleware: every answer, also a refusal, tells the browser to use HTTPS only (after the first visit), to trust
    the content types, to send the address only within the app and never to show the app in a frame (SPEC 7.4)."""

    def process_response(self, req: falcon.Request, resp: falcon.Response, resource: object, req_succeeded: bool) -> None:
        resp.set_headers(SECURITY_HEADERS)


class RevalidateStaticFiles:
    """Middleware: browsers re-check static files on each use (cheap thanks to their ETag), so changes show at once."""

    def process_response(self, req: falcon.Request, resp: falcon.Response, resource: object, req_succeeded: bool) -> None:
        if req.path.startswith('/static/'):
            resp.set_header('Cache-Control', 'no-cache')
