"""Local development server: python -m src (host and port from $WORK_TRACKER_HOST / $WORK_TRACKER_PORT)."""

import os
import sys
from wsgiref.simple_server import make_server

from src.app import create_app
from src.utils.stages import StageError


def main() -> None:
    host = os.environ.get('WORK_TRACKER_HOST', '127.0.0.1')
    port = int(os.environ.get('WORK_TRACKER_PORT', '8000'))
    try:
        app = create_app()
    except StageError as error:
        sys.exit(f'Work Tracker cannot start: {error}')
    with make_server(host, port, app) as server:
        print(f'Work Tracker on http://{host}:{port}/ (API docs: /apidoc/swagger)')
        server.serve_forever()


if __name__ == '__main__':
    main()
