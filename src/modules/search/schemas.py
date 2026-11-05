"""Search: a user's entries of a period found by text, service or activity type, summed up by ticket or activity type
and by month."""

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
        'Words that all must match, ignoring case: the start of the ticket key, or a part of the description or note'))
    service_id: str | None = Field(
        default=None, description=f'Only ticket entries of this service; `{NO_SERVICE}`: tickets without service')
    activity_type_id: str | None = Field(default=None, description='Only activity entries of this type')
    start: dt.date | None = Field(default=None, description='First day; default: 1 January of this year')
    end: dt.date | None = Field(default=None, description='Last day; default: 31 December of this year')

    @model_validator(mode='after')
    def check_period(self) -> Self:
        if self.start and self.end and self.end < self.start:
            raise ValueError('end must be on or after start')
        return self

    def period(self, today: dt.date) -> tuple[dt.date, dt.date]:
        return self.start or dt.date(today.year, 1, 1), self.end or dt.date(today.year, 12, 31)


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
    start: dt.date
    end: dt.date
    duration: str = Field(description='The hours of all entries found')
    count: int
    groups: list[SearchGroup] = Field(description='By ticket or activity type, the most hours first')
    months: list[SearchMonth] = Field(description='By month, the months with entries found')
    entries: list[EntryView] = Field(description='The entries found, newest first')


def search(store: Store, user_id: str, query: SearchQuery, today: dt.date) -> SearchResult:
    start, end = query.period(today)
    views = EntryViewer(store, user_id).views(store.entries(user_id).between(start, end))
    words = query.text.casefold().split()
    found = [view for view in views if _in_scope(view, query) and all(_matches(view, word) for word in words)]
    return SearchResult(
        start=start, end=end, duration=_total(found), count=len(found),
        groups=_groups(found), months=_months(found),
        entries=sorted(found, key=lambda view: view.date, reverse=True),
    )


def _in_scope(view: EntryView, query: SearchQuery) -> bool:
    """Of the activity type and of the service asked for, if any."""
    if query.activity_type_id is not None and view.activity_type_id != query.activity_type_id:
        return False
    if query.service_id is None:
        return True
    return view.kind == 'ticket' and view.service_id == (None if query.service_id == NO_SERVICE else query.service_id)


def _matches(view: EntryView, word: str) -> bool:
    """The word starts the ticket key or is part of the description or note."""
    return (view.ticket_key or '').casefold().startswith(word) or word in (view.description or view.note or '').casefold()


def _groups(found: list[EntryView]) -> list[SearchGroup]:
    grouped = defaultdict(list)
    for view in found:
        grouped[view.kind, view.ticket_key if view.kind == 'ticket' else view.activity_type].append(view)
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
