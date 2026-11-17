"""The login status: what `GET /api/auth/status` answers and every page carries in its HTML (SPEC 5.6), so a page need
not ask for it."""

import datetime as dt
from collections.abc import Callable

from src.modules.auth.schemas import AuthStatus, UserView
from src.modules.auth.setup_token import SetupToken
from src.modules.storage.store import Store
from src.modules.teams.schemas import TeamRef


class LoginStatus:
    def __init__(self, clock: Callable[[], dt.datetime], enabled: bool = True, setup_token: SetupToken | None = None) -> None:
        self._clock = clock
        self._enabled = enabled
        self._setup_token = setup_token

    def read(self, store: Store, user_id: str | None) -> AuthStatus:
        """Whether the login is on, whether users and root exist, who is logged in (with their team, number of open
        invitations, whether they audit a team and, for support, the number of new contact messages), whether new users
        can register, and whether creating root needs the setup token. With the login off, nobody is logged in."""
        logged_in = self._enabled and user_id is not None
        status = self._without_user(store, has_users=logged_in)
        return _with_user(status, store, user_id, self._clock().date()) if logged_in else status

    def _without_user(self, store: Store, has_users: bool) -> AuthStatus:
        """The status for anyone; the users are counted only if nobody is logged in (TASKS.md 14.4c)."""
        users, token = store.users(), self._setup_token is not None
        has_root = users.root_id() is not None
        return AuthStatus(enabled=self._enabled, has_users=has_users or users.count() > 0, has_root=has_root, user=None,
                          registration=self._enabled and store.registration_open(), setup_token=token and not has_root,
                          root_reset=token and has_root)


def _with_user(status: AuthStatus, store: Store, user_id: str, today: dt.date) -> AuthStatus:
    """The logged-in user, with their team, number of open invitations, whether they audit a team today and, for
    support, the number of new contact messages."""
    membership, user = store.teams().membership(user_id), store.users().get(user_id)
    new = sum(message.status == 'new' for message in store.messages().all()) if user.support else 0
    return status.model_copy(update={'user': UserView.of(user), 'new_messages': new,
                                     'team': TeamRef.of(membership) if membership else None,
                                     'invitations': len(store.invitations().of_user(user_id)),
                                     'auditor': any(auditor.active(today) for auditor in store.auditors().of_user(user_id))})
