"""Turning the comment lines of a sheet row into task entries and day notes (one line = one entry)."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from src.lib.durations import split_evenly
from src.modules.importer.lines import split_hours

TICKET_PREFIXES = ('KP', 'TNG', 'ENGINE', 'AGA', 'MSI')
TICKET = re.compile(rf'\b(?:{"|".join(TICKET_PREFIXES)})-[1-9]\d*\b')
_LEADING_TICKETS = re.compile(rf'(?:{TICKET.pattern}\s*(?:,|/|&|\band\b)?\s*)+[:\-–]?\s*')

_PR_REVIEW = re.compile(r'PR\b', re.IGNORECASE)
_MEETING = re.compile(r'Meeting(?:\(s\))?:\s*', re.IGNORECASE)  # the prefix is dropped from the note
_MEETING_NAMES = re.compile(
    r'(?:Meetings?|Tactical Meeting|Teamstufe Meeting|Standup|Retro(?:spective)?|Planning)\b', re.IGNORECASE
)
_TOOL_MANAGEMENT = re.compile(r'(?:Tool Management|TM\b|GCC \(Tool Management\))', re.IGNORECASE)
_TOOL_MANAGEMENT_NAMES = re.compile(r'GCC \(Tool Management\)|Tool Management|\(TM\)|\bTM\b', re.IGNORECASE)
_TRAVEL = re.compile(r'A[nb](?:reise|fahrt)\b', re.IGNORECASE)

TOOL_MANAGEMENT, MEETING, TRAVEL, OTHER = 'Tool Management', 'Meeting', 'Travel', 'Other'


@dataclass(frozen=True)
class ParsedEntry:
    """A task entry from one comment line: a ticket entry, or an activity entry if `activity` is set."""

    duration: int
    source: str  # the original comment line, kept in the entry's history
    ticket_key: str | None = None
    activity: str | None = None  # activity type name
    text: str = ''  # description of a ticket entry, note of an activity entry
    coding: bool = False


@dataclass(frozen=True)
class ParsedComment:
    entries: tuple[ParsedEntry, ...]
    notes: tuple[str, ...]  # lines without hours or ticket, for the day note


def parse_comment(lines: Iterable[str]) -> ParsedComment:
    entries, notes = [], []
    for line in lines:
        if parsed := parse_line(line):
            entries.extend(parsed)
        else:
            notes.append(line)
    return ParsedComment(tuple(entries), tuple(notes))


def parse_line(line: str) -> list[ParsedEntry]:
    """The entries of one comment line; empty if the line is a note (no hours and no ticket)."""
    minutes, rest = split_hours(line)
    tickets = list(dict.fromkeys(TICKET.findall(rest)))
    if minutes is None:
        return [ParsedEntry(0, line, key, text=_description(rest), coding=True) for key in tickets]
    if tickets and not _is_meeting(rest):
        return _ticket_entries(minutes, line, rest, tickets)
    return [_activity_entry(minutes, line, rest)]


def _is_meeting(rest: str) -> bool:
    return bool(_MEETING.match(rest) or _MEETING_NAMES.match(rest))


def _ticket_entries(minutes: int, line: str, rest: str, tickets: list[str]) -> list[ParsedEntry]:
    """One entry per ticket, the hours split evenly in quarter hours."""
    description = _description(rest)
    shares = split_evenly(minutes, len(tickets))
    return [ParsedEntry(share, line, key, text=description, coding=True) for key, share in zip(tickets, shares)]


def _description(rest: str) -> str:
    """The text without leading tickets ('KP-1951: data mapping' → 'data mapping'); tickets inside the text stay."""
    match = _LEADING_TICKETS.match(rest)
    return rest[match.end():].strip() if match else rest


def _activity_entry(minutes: int, line: str, rest: str) -> ParsedEntry:
    if _PR_REVIEW.match(rest):
        return ParsedEntry(minutes, line, text=rest, coding=True)  # a PR review without ticket, for review
    if match := _MEETING.match(rest):
        return ParsedEntry(minutes, line, activity=MEETING, text=rest[match.end():])
    if _MEETING_NAMES.match(rest):
        return ParsedEntry(minutes, line, activity=MEETING, text=rest)  # e.g. 'Standup', 'Tactical Meeting'
    if _TOOL_MANAGEMENT.match(rest):
        return ParsedEntry(minutes, line, activity=TOOL_MANAGEMENT, text=_TOOL_MANAGEMENT_NAMES.sub('', rest).strip(' ()'))
    activity = TRAVEL if _TRAVEL.match(rest) else OTHER
    return ParsedEntry(minutes, line, activity=activity, text=rest)
