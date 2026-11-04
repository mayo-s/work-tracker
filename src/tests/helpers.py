"""Helpers of many tests: logging in through the API, a clock to set, a step in a transaction of its own."""

import datetime as dt
from collections.abc import Callable

from falcon import testing

from src.tests.users import PASSWORD


def login(client: testing.TestClient, name: str, password: str = PASSWORD, cookies: dict[str, str] | None = None,
          **fields: object) -> testing.Result:
    """The answer to a login with username or e-mail address; `fields`, e.g. `code` or `remember`."""
    return client.simulate_post('/api/auth/login', cookies=cookies, json={'login': name, 'password': password, **fields})


def session(result: testing.Result) -> dict[str, str]:
    """The session cookie of an answer, to send along."""
    return {'wt_session': result.cookies['wt_session'].value}


def logged_in(client: testing.TestClient, name: str, password: str = PASSWORD, **fields: object) -> dict[str, str]:
    """The session cookie of a successful login."""
    return session(login(client, name, password, **fields))


class Clock:
    """`now()` for the app or a repository; the test moves `now` on."""

    def __init__(self, now: dt.datetime) -> None:
        self.now = now

    def __call__(self) -> dt.datetime:
        return self.now


def run[T](storage: object, action: Callable[[object], T]) -> T:
    """`action(store)` in a transaction of its own, so the next step sees what was stored."""
    with storage.transaction() as store:
        return action(store)
