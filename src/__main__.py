"""Local development server: python -m src (host and port from $WORK_TRACKER_HOST / $WORK_TRACKER_PORT)."""

import os
import sys
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from src.app import create_app
from src.utils.stages import StageError


class Server(ThreadingMixIn, WSGIServer):
    """Answers requests side by side: a page loads about 20 modules at once, which a server answering one at a time
    with the default queue of 5 partly drops (the page then stays empty). Each transaction has its own connection."""

    daemon_threads = True
    request_queue_size = 64


def main() -> None:
    host = os.environ.get('WORK_TRACKER_HOST', '127.0.0.1')
    port = int(os.environ.get('WORK_TRACKER_PORT', '8000'))
    try:
        app = create_app()
    except StageError as error:
        sys.exit(f'Work Tracker cannot start: {error}')
    with make_server(host, port, app, server_class=Server) as server:
        print(f'Work Tracker on http://{host}:{port}/ (API docs: /apidoc/swagger)')
        server.serve_forever()


if __name__ == '__main__':
    main()
