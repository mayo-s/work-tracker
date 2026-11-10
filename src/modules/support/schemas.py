"""What support sees of the contact messages and changes about them (SPEC 5.14)."""

import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from src.models.messages import ChangeKind, ContactMessage, MessageChange, MessageStatus


class SupportQuery(BaseModel):
    text: str = Field(default='', max_length=200, description='Words that all must match, ignoring case: in the subject, '
                                                              'the message or a note')


class StatusInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: MessageStatus = Field(description='New, in progress or done; a done message can be reopened')


class NoteInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=5000, description='An internal note, which only support sees')


class MessageChangeView(BaseModel):
    at: dt.datetime
    actor: str = Field(description='Who made it, or "Support" once the message is archived')
    kind: ChangeKind
    detail: str = Field(description='The new status, or the note')

    @classmethod
    def of(cls, change: MessageChange) -> Self:
        return cls(at=change.at, actor=change.actor_name, kind=change.kind, detail=change.detail)


class MessageView(BaseModel):
    id: str
    sent_at: dt.datetime
    name: str = Field(description='The sender, or a color and an animal once archived')
    email: str = Field(description='To answer to; empty once archived')
    username: str | None = Field(description='The sender\'s username, if they were logged in (not once archived)')
    known: bool = Field(description='Sent by a logged-in user (also in the archive)')
    subject: str
    text: str
    status: MessageStatus
    done_at: dt.datetime | None = Field(description='When it was last marked Done')
    archived: bool = Field(description='Anonymized 90 days after it was last marked Done; it stays as it is')
    changes: list[MessageChangeView] = Field(description='Status changes and notes, oldest first')

    @classmethod
    def of(cls, message: ContactMessage, username: str | None, changes: list[MessageChange]) -> Self:
        return cls(**message.model_dump(include={'id', 'sent_at', 'name', 'email', 'known', 'subject', 'text', 'status',
                                                 'done_at'}),
                   username=username, archived=message.anonymized, changes=[MessageChangeView.of(item) for item in changes])


class SupportMessages(BaseModel):
    messages: list[MessageView] = Field(description='The open ones and the done ones of the last 90 days, newest first')
    archive: list[MessageView] = Field(description='The anonymized ones, newest first')
