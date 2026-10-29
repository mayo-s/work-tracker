"""Frontend pages: the shared frame (src/templates/frame.html) around a page's content (src/templates/pages)."""

import sqlite3
from pathlib import Path

import falcon

from src.modules.storage.database import Database
from src.modules.storage.owners import NO_OWNER
from src.modules.storage.settings import load_theme, registration_open, setup_done
from src.modules.storage.users import UserRepository

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / 'templates'
STATIC_DIR = TEMPLATES_DIR / 'static'


def render_page(name: str, title: str, theme: str = 'system') -> str:
    """The frame with the page's title, name, content and color theme filled in (`system` sets no theme)."""
    frame = (TEMPLATES_DIR / 'frame.html').read_text(encoding='utf-8')
    content = (TEMPLATES_DIR / 'pages' / f'{name}.html').read_text(encoding='utf-8').rstrip('\n')
    theme_attribute = '' if theme == 'system' else f' data-theme="{theme}"'
    return (frame.replace('{{title}}', title).replace('{{page}}', name).replace('{{theme}}', theme_attribute)
            .replace('{{content}}', content))


class Page:
    """Serves one page; files are read on each request, so template changes show without a restart."""

    def __init__(self, name: str, title: str) -> None:
        self.name = name
        self._title = title

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.content_type = falcon.MEDIA_HTML
        resp.text = render_page(self.name, self._title, req.context.get('theme', 'system'))


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

    def __init__(self, database: Database, enabled: bool) -> None:
        super().__init__('register', 'Register')
        self._database = database
        self._enabled = enabled

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        with self._database.transaction() as conn:
            if not (self._enabled and registration_open(conn)):
                raise falcon.HTTPNotFound(description='Registration is switched off')
        super().on_get(req, resp)


class PageSettings:
    """Middleware for pages: the color theme for the frame; until the database is set up, pages forward to /setup,
    and /setup forwards to the week once it is."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def process_resource(self, req: falcon.Request, resp: falcon.Response, resource: object, params: dict) -> None:
        if not isinstance(resource, Page):
            return
        user_id = req.context.get('user_id')
        with self._database.transaction() as conn:
            done = _set_up(conn, user_id)
            req.context.theme = load_theme(conn, NO_OWNER if user_id is None else user_id)
        if done == (resource.name == 'setup'):
            raise falcon.HTTPSeeOther('/' if done else '/setup')


def _set_up(conn: sqlite3.Connection, user_id: str | None) -> bool:
    """The user's setup state; not logged in, only a database without users is set up first (the login handles the
    rest)."""
    if user_id is not None:
        return setup_done(conn, user_id)
    return bool(UserRepository(conn).count()) or setup_done(conn, NO_OWNER)


class Redirect:
    """Forwards a former page address, e.g. /lists to /settings#services."""

    def __init__(self, location: str) -> None:
        self._location = location

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        raise falcon.HTTPMovedPermanently(self._location)


class RevalidateStaticFiles:
    """Middleware: browsers re-check static files on each use (cheap thanks to their ETag), so changes show at once."""

    def process_response(self, req: falcon.Request, resp: falcon.Response, resource: object, req_succeeded: bool) -> None:
        if req.path.startswith('/static/'):
            resp.set_header('Cache-Control', 'no-cache')
