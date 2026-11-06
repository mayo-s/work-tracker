"""Search: a user's entries found by text, service or activity type, of all time or a period, summed up by ticket or
activity type and by month."""

import datetime as dt
from collections import defaultdict
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from src.lib.durations import format_duration, parse_duration
from src.modules.entries.schemas import EntryView, EntryViewer
from src.modules.storage.store import Store

NO_SERVICE = 'none'


class SearchQuery(BaseModel):
    text: str = Field(default='', max_length=200, description=(
        'Words that all must match, ignoring case: the start of the ticket key, or a part of the description, '
        'of the service (short name or name) or of the activity type'))
    service_id: str | None = Field(
        default=None, description=f'Only ticket entries of this service; `{NO_SERVICE}`: tickets without service')
    activity_type_id: str | None = Field(default=None, description='Only activity entries of this type')
    start: dt.date | None = Field(default=None, description='First day; none: from the first entry')
    end: dt.date | None = Field(default=None, description='Last day; none: up to the last entry')
    limit: int | None = Field(default=None, ge=1, description='List only the newest entries found; the sums count all')

    @model_validator(mode='after')
    def check_period(self) -> Self:
        if self.start and self.end and self.end < self.start:
            raise ValueError('end must be on or after start')
        return self


class SearchGroup(BaseModel):
    kind: Literal['ticket', 'activity']
    key: str | None = Field(description='Ticket key or activity type; null for ticket entries without ticket')
    duration: str
    entries: int


class SearchMonth(BaseModel):
    month: str = Field(examples=['2026-10'])
    duration: str
    entries: int


class SearchResult(BaseModel):
    duration: str = Field(description='The hours of all entries found')
    count: int = Field(description='The number of all entries found')
    groups: list[SearchGroup] = Field(description='By ticket or activity type, the most hours first')
    months: list[SearchMonth] = Field(description='By month, the months with entries found')
    entries: list[EntryView] = Field(description='The entries found, newest first (the newest `limit` ones)')


def search(store: Store, user_id: str, query: SearchQuery) -> SearchResult:
    entries = store.entries(user_id).between(query.start or dt.date.min, query.end or dt.date.max)
    service_names = {service.id: service.name for service in store.services(user_id).choices()}
    found = _found(EntryViewer(store, user_id).views(entries), query, service_names)
    return SearchResult(
        duration=_total(found), count=len(found), groups=_groups(found), months=_months(found),
        entries=sorted(found, key=lambda view: view.date, reverse=True)[:query.limit],
    )


def _found(views: list[EntryView], query: SearchQuery, service_names: dict[str | None, str]) -> list[EntryView]:
    words = query.text.casefold().split()
    return [view for view in views if _in_scope(view, query) and _matches(view, words, service_names)]


def _in_scope(view: EntryView, query: SearchQuery) -> bool:
    """Of the activity type and of the service asked for, if any."""
    if query.activity_type_id is not None and view.activity_type_id != query.activity_type_id:
        return False
    if query.service_id is None:
        return True
    return view.ticket_key is not None and view.service_id == (None if query.service_id == NO_SERVICE else query.service_id)


def _matches(view: EntryView, words: list[str], service_names: dict[str | None, str]) -> bool:
    """Every word starts the ticket key or is part of the description, of the service (short name or name) or
    of the activity type."""
    key, text = (view.ticket_key or '').casefold(), _text(view, service_names)
    return all(key.startswith(word) or word in text for word in words)


def _text(view: EntryView, service_names: dict[str | None, str]) -> str:
    """The texts a word may be part of, one per line (a word does not span two), ignoring case."""
    texts = (view.description, view.service, service_names.get(view.service_id), view.activity_type)
    return '\n'.join(part for part in texts if part).casefold()


def _groups(found: list[EntryView]) -> list[SearchGroup]:
    grouped = defaultdict(list)
    for view in found:
        kind = 'ticket' if view.ticket_key else 'activity'  # by ticket, or by activity type without one (TASKS.md 13.9)
        grouped[kind, view.ticket_key or view.activity_type].append(view)
    groups = [SearchGroup(kind=kind, key=key, duration=_total(views), entries=len(views))
              for (kind, key), views in grouped.items()]
    return sorted(groups, key=lambda group: (-parse_duration(group.duration), group.key or ''))


def _months(found: list[EntryView]) -> list[SearchMonth]:
    grouped = defaultdict(list)
    for view in found:
        grouped[view.date.strftime('%Y-%m')].append(view)
    return [SearchMonth(month=month, duration=_total(views), entries=len(views)) for month, views in sorted(grouped.items())]


def _total(views: list[EntryView]) -> str:
    return format_duration(sum(parse_duration(view.duration) for view in views))
