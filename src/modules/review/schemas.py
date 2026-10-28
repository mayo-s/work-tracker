"""API schemas for the review list: what needs attention after the import, and why."""

import sqlite3
from collections import defaultdict
from enum import StrEnum

from pydantic import BaseModel, Field

from src.models.review import FlagReason
from src.modules.days.schemas import DayView, day_view
from src.modules.entries.schemas import EntryView, EntryViewer
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.tickets import TicketRepository
from src.modules.tickets.schemas import TicketView, ticket_views


class ReviewReason(StrEnum):
    ZERO_DURATION = 'zero_duration'  # 0:00, e.g. a ticket mentioned without hours
    NO_TICKET = 'no_ticket'  # a ticket entry without ticket, e.g. an imported PR review
    UNCERTAIN_TICKET = FlagReason.UNCERTAIN_TICKET.value  # import flag: the ticket key was guessed


class ReviewEntry(BaseModel):
    entry: EntryView
    reasons: list[ReviewReason]


class ReviewCounts(BaseModel):
    tickets_without_service: int
    entries: int
    days: int


class ReviewView(BaseModel):
    counts: ReviewCounts
    tickets_without_service: list[TicketView] = Field(description='Tickets with entries but no service; assign one per ticket')
    entries: list[ReviewEntry] = Field(description='Entries with 0:00, without ticket or with an import flag, by date')
    days: list[DayView] = Field(description='Days with import flags (e.g. weekend hours), by date')


def review(conn: sqlite3.Connection) -> ReviewView:
    tickets = [ticket for ticket in ticket_views(conn, TicketRepository(conn).without_service()) if ticket.entries]
    views = EntryViewer(conn).views(EntryRepository(conn).for_review())
    entries = [ReviewEntry(entry=view, reasons=_reasons(view)) for view in views]
    days = _flagged_days(conn)
    return ReviewView(
        counts=ReviewCounts(tickets_without_service=len(tickets), entries=len(entries), days=len(days)),
        tickets_without_service=tickets,
        entries=entries,
        days=days,
    )


def _reasons(entry: EntryView) -> list[ReviewReason]:
    reasons = [ReviewReason(flag.reason.value) for flag in entry.flags]
    if entry.duration == '0:00':
        reasons.append(ReviewReason.ZERO_DURATION)
    if entry.kind == 'ticket' and entry.ticket_key is None:
        reasons.append(ReviewReason.NO_TICKET)
    return list(dict.fromkeys(reasons))


def _flagged_days(conn: sqlite3.Connection) -> list[DayView]:
    days = DayRepository(conn)
    flags = defaultdict(list)
    for flag in days.day_flags():
        flags[flag.date].append(flag)
    return [day_view(date, days.get(date), date_flags) for date, date_flags in flags.items()]
