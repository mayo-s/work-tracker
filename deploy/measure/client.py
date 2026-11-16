"""The app over HTTP for the measuring scripts: logged in as $WT_LOGIN with $WT_PASSWORD (an account without
two-factor login), on one connection, with the time every call took and what the app said it took (`Server-Timing`,
on a stage with WORK_TRACKER_TIMING=on)."""

import http.client
import json
import os
import re
import time
from typing import Any, NamedTuple
from urllib.parse import urlsplit

_TIMING = re.compile(r'(\w+);dur=([\d.]+)(?:;desc="(\d+) calls, (\d+) items")?')


class Answer(NamedTuple):
    data: Any  # the JSON answer; None for a page
    took: float  # ms, as seen from here
    size: int  # bytes
    timing: dict[str, float]  # of `Server-Timing`: app, db and first in ms, calls, items


def server_timing(header: str | None) -> dict[str, float]:
    """`app;dur=84.3, db;dur=51.2;desc="12 calls, 2293 items"` as app, db, calls and items (and `first`, if there)."""
    timing = {}
    for name, duration, calls, items in _TIMING.findall(header or ''):
        timing[name] = float(duration)
        if calls:
            timing |= {'calls': int(calls), 'items': int(items)}
    return timing


class App:
    def __init__(self, base_url: str) -> None:
        url = urlsplit(base_url)
        self._connection_type = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
        self._host = url.netloc
        self._connection = self._connection_type(self._host, timeout=90)
        self._headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        self._headers['Cookie'] = self._log_in()

    def _log_in(self) -> str:
        """The session cookie of a new login."""
        login = {'login': os.environ['WT_LOGIN'], 'password': os.environ['WT_PASSWORD'], 'code': None, 'remember': False}
        response = self._send('POST', '/api/auth/login', json.dumps(login))
        if response.status != 200:
            raise SystemExit(f'Login as {login["login"]}: HTTP {response.status} {response.read()[:300]!r}')
        response.read()
        return response.getheader('Set-Cookie').split(';')[0]

    def _send(self, method: str, path: str, payload: str | None) -> http.client.HTTPResponse:
        """Sends the request, once more on a new connection if the old one was closed meanwhile."""
        try:
            self._connection.request(method, path, body=payload, headers=self._headers)
            return self._connection.getresponse()
        except (http.client.HTTPException, OSError):
            self._connection.close()
            self._connection = self._connection_type(self._host, timeout=90)
            self._connection.request(method, path, body=payload, headers=self._headers)
            return self._connection.getresponse()

    def call(self, method: str, path: str, body: object = None) -> Answer:
        """The answer of the app; anything but a success ends the script."""
        started = time.perf_counter()
        response = self._send(method, path, None if body is None else json.dumps(body))
        content = response.read()
        took = (time.perf_counter() - started) * 1000
        if response.status >= 400:
            raise SystemExit(f'{method} {path}: HTTP {response.status} {content[:300]!r}')
        is_json = response.getheader('Content-Type', '').startswith('application/json')
        return Answer(json.loads(content) if content and is_json else None, took, len(content),
                      server_timing(response.getheader('Server-Timing')))
