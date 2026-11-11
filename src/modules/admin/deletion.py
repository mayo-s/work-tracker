"""Deleting an account (SPEC 5.7, GDPR Art. 17): by an admin on request, or by the user in their settings."""

import datetime as dt
import random

from src.modules.admin.audit import record
from src.modules.storage.store import Store
from src.modules.support.archive import Choose, pseudonym


def delete_account(store: Store, user_id: str, actor_id: str, now: dt.datetime, choose: Choose = random.choice) -> None:
    """The account goes with everything of theirs; their contact messages are anonymized first, as in the archive. The
    audit log keeps who deleted an account and when, not whose (`own` when the user deleted it)."""
    messages = store.messages()
    for message in messages.all():
        if message.user_id == user_id:
            messages.anonymize(message.id, pseudonym(choose))
    store.delete_user(user_id)
    record(store, now, actor_id, 'account_deleted', detail='own' if actor_id == user_id else '')
