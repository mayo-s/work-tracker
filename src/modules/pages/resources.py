"""Frontend pages: the shared frame (src/templates/frame.html) around a page's content (src/templates/pages)."""

from pathlib import Path

import falcon

from src.modules.storage.database import Database
from src.modules.storage.settings import setup_done

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / 'templates'
STATIC_DIR = TEMPLATES_DIR / 'static'


def render_page(name: str, title: str) -> str:
    """The frame with the page's title, name and content filled in."""
    frame = (TEMPLATES_DIR / 'frame.html').read_text(encoding='utf-8')
    content = (TEMPLATES_DIR / 'pages' / f'{name}.html').read_text(encoding='utf-8').rstrip('\n')
    return frame.replace('{{title}}', title).replace('{{page}}', name).replace('{{content}}', content)


class Page:
    """Serves one page; files are read on each request, so template changes show without a restart."""

    def __init__(self, name: str, title: str) -> None:
        self.name = name
        self._title = title

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.content_type = falcon.MEDIA_HTML
        resp.text = render_page(self.name, self._title)


class SetupGate:
    """Middleware: pages forward to /setup until the database is set up, and /setup to the week once it is."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def process_resource(self, req: falcon.Request, resp: falcon.Response, resource: object, params: dict) -> None:
        if not isinstance(resource, Page):
            return
        with self._database.transaction() as conn:
            done = setup_done(conn)
        if done == (resource.name == 'setup'):
            raise falcon.HTTPSeeOther('/' if done else '/setup')


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
