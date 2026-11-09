"""API schemas for the review list: what needs attention, and why."""

from enum import StrEnum

from pydantic import BaseModel, Field

from src.models.catalog import Ticket
from src.modules.entries.schemas import EntryView, EntryViewer
from src.modules.storage.store import Store
from src.modules.tickets.schemas import TicketView, ticket_views


class ReviewReason(StrEnum):
    ZERO_DURATION = 'zero_duration'  # 0:00
    NO_TICKET = 'no_ticket'  # no ticket, though the activity type requires one
    NO_ACTIVITY_TYPE = 'no_activity_type'  # a former ticket entry whose activity was unclear (SPEC 4.6)


class ReviewEntry(BaseModel):
    entry: EntryView
    reasons: list[ReviewReason]


class ReviewCounts(BaseModel):
    tickets_without_service: int
    entries: int


class ReviewView(BaseModel):
    counts: ReviewCounts
    tickets_without_service: list[TicketView] = Field(description='Tickets with entries but no service; assign one per ticket')
    entries: list[ReviewEntry] = Field(
        description='Entries with 0:00, without activity type or without the ticket it requires, by date')


def review(store: Store, user_id: str) -> ReviewView:
    """What needs attention in the user's data."""
    tickets = ticket_views(store, user_id, _open_tickets(store, user_id))
    views = EntryViewer(store, user_id).views(store.entries(user_id).for_review())
    entries = [ReviewEntry(entry=view, reasons=_reasons(view)) for view in views]
    return ReviewView(
        counts=ReviewCounts(tickets_without_service=len(tickets), entries=len(entries)),
        tickets_without_service=tickets,
        entries=entries,
    )


def review_counts(store: Store, user_id: str) -> ReviewCounts:
    """The number of open items of each kind, without building them (for the navigation and the dashboard)."""
    return ReviewCounts(tickets_without_service=len(_open_tickets(store, user_id)),
                        entries=len(store.entries(user_id).for_review()))


def _open_tickets(store: Store, user_id: str) -> list[Ticket]:
    """Tickets with entries but no service."""
    tickets = store.tickets(user_id)
    counts = tickets.entry_counts()
    return [ticket for ticket in tickets.without_service() if counts.get(ticket.key)]


def _reasons(entry: EntryView) -> list[ReviewReason]:
    reasons = []
    if entry.duration == '0:00':
        reasons.append(ReviewReason.ZERO_DURATION)
    if entry.activity_type_id is None:
        reasons.append(ReviewReason.NO_ACTIVITY_TYPE)
    if entry.ticket_required and entry.ticket_key is None:
        reasons.append(ReviewReason.NO_TICKET)
    return reasons
