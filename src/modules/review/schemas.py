"""API schemas for the review list: what needs attention after the import, and why."""

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, Field

from src.lib.durations import format_duration

from src.models.catalog import Ticket
from src.models.entries import Entry, TicketEntry
from src.models.review import FlagReason, ReviewFlag
from src.modules.days.schemas import DayView, day_view
from src.modules.entries.schemas import EntryView, EntryViewer
from src.modules.importer.tickets import split_keys
from src.modules.storage.store import Entries, Store
from src.modules.tickets.schemas import TicketView, ticket_views


class ReviewReason(StrEnum):
    ZERO_DURATION = 'zero_duration'  # 0:00, e.g. a ticket mentioned without hours
    NO_TICKET = 'no_ticket'  # a ticket entry without ticket, e.g. an imported PR review
    UNCERTAIN_TICKET = FlagReason.UNCERTAIN_TICKET.value  # import flag: the ticket key was guessed


class SplitPart(BaseModel):
    ticket_key: str | None
    duration: str


class ReviewEntry(BaseModel):
    entry: EntryView
    reasons: list[ReviewReason]
    original: str | None = Field(description='The spreadsheet line the entry was imported from; null if not imported')
    split_on_import: list[SplitPart] = Field(
        description='All entries the import made from the same spreadsheet line, if it named several tickets')
    split_suggestion: list[str] = Field(
        description='Tickets to split the entry among, if its spreadsheet line named an alias or "ff"; empty otherwise')


class ReviewCounts(BaseModel):
    tickets_without_service: int
    entries: int
    days: int


class ReviewView(BaseModel):
    counts: ReviewCounts
    tickets_without_service: list[TicketView] = Field(description='Tickets with entries but no service; assign one per ticket')
    entries: list[ReviewEntry] = Field(description='Entries with 0:00, without ticket or with an import flag, by date')
    days: list[DayView] = Field(description='Days with import flags (e.g. weekend hours), by date')


def review(store: Store, user_id: str) -> ReviewView:
    """What needs attention in the user's data."""
    tickets = ticket_views(store, user_id, _open_tickets(store, user_id))
    repository = store.entries(user_id)
    views = EntryViewer(store, user_id).views(repository.for_review())
    on_dates = _entries_on(repository, views)
    lines = repository.imported_lines(entry.id for entry in on_dates)
    split = _split_on_import(on_dates, lines)
    entries = [
        ReviewEntry(entry=view, reasons=_reasons(view), original=lines.get(view.id), split_on_import=split.get(view.id, []),
                    split_suggestion=_split_suggestion(view))
        for view in views
    ]
    days = _flagged_days(store, user_id)
    return ReviewView(
        counts=ReviewCounts(tickets_without_service=len(tickets), entries=len(entries), days=len(days)),
        tickets_without_service=tickets,
        entries=entries,
        days=days,
    )


def review_counts(store: Store, user_id: str) -> ReviewCounts:
    """The number of open items of each kind, without building them (for the navigation and the dashboard)."""
    return ReviewCounts(
        tickets_without_service=len(_open_tickets(store, user_id)),
        entries=len(store.entries(user_id).for_review()),
        days=len(_day_flags(store, user_id)),
    )


def _open_tickets(store: Store, user_id: str) -> list[Ticket]:
    """Tickets with entries but no service."""
    tickets = store.tickets(user_id)
    counts = tickets.entry_counts()
    return [ticket for ticket in tickets.without_service() if counts.get(ticket.key)]


def _entries_on(repository: Entries, views: list[EntryView]) -> list[Entry]:
    """The entries on the dates of the given entries, in one query."""
    dates = {view.date for view in views}
    if not dates:
        return []
    return [entry for entry in repository.between(min(dates), max(dates)) if entry.date in dates]


def _split_on_import(entries: list[Entry], lines: dict[str, str]) -> dict[str, list[SplitPart]]:
    """The parts of each ticket entry the import made from a spreadsheet line naming several tickets, by entry id."""
    split: dict[str, list[SplitPart]] = {}
    for together in _imported_together(entries, lines):
        if len(together) > 1:
            parts = [SplitPart(ticket_key=entry.ticket_key, duration=format_duration(entry.duration)) for entry in together]
            split.update(dict.fromkeys((entry.id for entry in together), parts))
    return split


def _imported_together(entries: list[Entry], lines: dict[str, str]) -> Iterable[list[TicketEntry]]:
    """The imported ticket entries, grouped by date and the spreadsheet line (`lines`, by entry id) they came from."""
    together = defaultdict(list)
    for entry in entries:
        if entry.id in lines and isinstance(entry, TicketEntry):
            together[entry.date, lines[entry.id]].append(entry)
    return together.values()


def _split_suggestion(entry: EntryView) -> list[str]:
    keys = [key for flag in entry.flags if flag.reason == FlagReason.UNCERTAIN_TICKET for key in split_keys(flag.detail)]
    return list(dict.fromkeys(keys))


def _reasons(entry: EntryView) -> list[ReviewReason]:
    reasons = [ReviewReason(flag.reason.value) for flag in entry.flags]
    if entry.duration == '0:00':
        reasons.append(ReviewReason.ZERO_DURATION)
    if entry.kind == 'ticket' and entry.ticket_key is None:
        reasons.append(ReviewReason.NO_TICKET)
    return list(dict.fromkeys(reasons))


def _flagged_days(store: Store, user_id: str) -> list[DayView]:
    days, schedules = store.days(user_id), store.schedules(user_id).schedules()
    return [day_view(date, days.get(date), flags, schedules.on(date)) for date, flags in _day_flags(store, user_id).items()]


def _day_flags(store: Store, user_id: str) -> dict[dt.date, list[ReviewFlag]]:
    """The flags of each flagged day, by date."""
    flags = defaultdict(list)
    for flag in store.days(user_id).day_flags():
        flags[flag.date].append(flag)
    return flags
