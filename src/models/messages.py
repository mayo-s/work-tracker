"""Messages of the contact page and what support did with them (SPEC 5.14)."""

import datetime as dt
from typing import Literal

from pydantic import Field

from src.models.base import DomainModel, RecordId

MessageStatus = Literal['new', 'in_progress', 'done']
ChangeKind = Literal['status', 'note']
SUPPORT = 'Support'  # who made a change, once the message is anonymized


class ContactMessage(DomainModel):
    """A message to the people running the app; anonymized 90 days after it was last marked Done (archive)."""

    id: RecordId | None = None
    sent_at: dt.datetime
    name: str = Field(min_length=1, max_length=100, description='The sender, or a color and an animal once anonymized')
    email: str = Field(default='', max_length=200, description='To answer to; empty once anonymized')
    subject: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=5000)
    user_id: str | None = Field(default=None, description="The sender's account, if they were logged in")
    known: bool = Field(default=False, description='Sent by a logged-in user; kept in the archive, unlike the account')
    status: MessageStatus = 'new'
    done_at: dt.datetime | None = Field(default=None, description='When it was last marked Done')
    anonymized: bool = False


class MessageChange(DomainModel):
    """A change support made to a message: its new status, or an internal note."""

    id: RecordId | None = None
    message_id: RecordId
    at: dt.datetime
    actor_id: str | None = Field(description='Who made it; None once the message is anonymized')
    kind: ChangeKind
    detail: str = Field(min_length=1, max_length=5000, description='The new status, or the note')
    actor_name: str = ''  # filled in when read: the name of the actor, or "Support"
