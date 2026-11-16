"""What answering a request took, as the `Server-Timing` header (SPEC 7.4), for measuring from outside: the time in
the app and, of it, the time waiting for DynamoDB with the number of calls and of items read.

Switched on with WORK_TRACKER_TIMING=on (as on the dev stage): the numbers tell how much data the app holds, so they
are nothing for every visitor.
"""

import contextvars
import itertools
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import falcon


@dataclass
class _Cost:
    started: float
    calls: int = 0
    items: int = 0
    waited: float = 0.0  # seconds in storage calls


_cost: contextvars.ContextVar[_Cost | None] = contextvars.ContextVar('cost', default=None)


def server_timing(enabled: bool | None = None) -> 'ServerTiming | None':
    """The middleware if measuring is on: as given or, by default, with WORK_TRACKER_TIMING=on."""
    if enabled is None:
        enabled = os.environ.get('WORK_TRACKER_TIMING', 'off').lower() == 'on'
    return ServerTiming() if enabled else None


def storage_call(call: Callable[..., dict[str, Any]], **arguments: Any) -> dict[str, Any]:
    """Calls DynamoDB and adds the call to the cost of the request being answered, with the items it read."""
    started = time.perf_counter()
    response = call(**arguments)
    cost = _cost.get()
    if cost:
        cost.calls += 1
        cost.items += len(response.get('Items', ())) + ('Item' in response)
        cost.waited += time.perf_counter() - started
    return response


def _milliseconds(seconds: float) -> str:
    return f'{seconds * 1000:.1f}'


class ServerTiming:
    """Middleware, the first one: `Server-Timing: app;dur=84.3, db;dur=51.2;desc="12 calls, 2293 items"` on every
    answer (times in ms; `db` only with storage calls). The first answer of an instance adds `first`, with the time
    since the app began to start: a short one says this request started the instance, a long one that it was kept
    warm."""

    def __init__(self) -> None:
        self._created = time.perf_counter()
        self._requests = itertools.count(1)

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        cost = _Cost(time.perf_counter())
        _cost.set(cost)
        if next(self._requests) == 1:
            req.context.since_start = cost.started - self._created

    def process_response(self, req: falcon.Request, resp: falcon.Response, resource: object, req_succeeded: bool) -> None:
        cost = _cost.get()
        metrics = [f'app;dur={_milliseconds(time.perf_counter() - cost.started)}']
        if cost.calls:
            metrics.append(f'db;dur={_milliseconds(cost.waited)};desc="{cost.calls} calls, {cost.items} items"')
        if 'since_start' in req.context:
            metrics.append(f'first;dur={_milliseconds(req.context.since_start)};desc="first request of the instance"')
        resp.set_header('Server-Timing', ', '.join(metrics))
        _cost.set(None)
