"""Change history of task entries."""

import datetime as dt
from enum import StrEnum

from pydantic import Field, JsonValue

from src.models.base import DomainModel


class HistoryAction(StrEnum):
    CREATED = 'created'
    IMPORTED = 'imported'
    UPDATED = 'updated'
    RENAMED = 'renamed'
    MERGED = 'merged'
    SPLIT = 'split'
    DELETED = 'deleted'


class EntryChange(DomainModel):
    """One line of an entry's history; `changes` maps each changed field to (old, new)."""

    id: int | None = None
    entry_id: int
    changed_at: dt.datetime
    action: HistoryAction
    changes: dict[str, tuple[JsonValue, JsonValue]] = Field(default_factory=dict)
    detail: str = Field(default='', max_length=500, description='e.g. the original spreadsheet line')
