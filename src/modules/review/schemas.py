"""API schemas for the review list: what needs attention after the import, and why."""

from collections import defaultdict
from enum import StrEnum

from pydantic import BaseModel, Field

from src.lib.durations import format_duration

from src.models.review import FlagReason
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
    without_service = store.tickets(user_id).without_service()
    tickets = [ticket for ticket in ticket_views(store, user_id, without_service) if ticket.entries]
    repository = store.entries(user_id)
    views = EntryViewer(store, user_id).views(repository.for_review())
    entries = [
        ReviewEntry(entry=view, reasons=_reasons(view), split_on_import=_split_on_import(repository, view),
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


def _split_on_import(repository: Entries, entry: EntryView) -> list[SplitPart]:
    together = repository.imported_together(entry.id) if entry.kind == 'ticket' else []
    if len(together) < 2:
        return []
    return [SplitPart(ticket_key=part.ticket_key, duration=format_duration(part.duration)) for part in together]


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
    flags = defaultdict(list)
    for flag in days.day_flags():
        flags[flag.date].append(flag)
    return [day_view(date, days.get(date), date_flags, schedules.on(date)) for date, date_flags in flags.items()]
