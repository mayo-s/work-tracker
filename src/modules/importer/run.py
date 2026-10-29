"""Importing one year of the spreadsheet into the database, in a single transaction."""

import datetime as dt
import sqlite3
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from src.lib.daytypes import DayType
from src.models.days import Day
from src.models.entries import ActivityEntry, Entry, TicketEntry
from src.models.history import HistoryAction
from src.models.review import FlagReason
from src.modules.importer.comments import ParsedEntry, parse_comment
from src.modules.importer.corrections import correct_day
from src.modules.importer.days import ImportedDay, classify_day
from src.modules.importer.reconcile import Reconciliation, reconcile
from src.modules.importer.sheet import SheetRow, read_sheet
from src.modules.storage.catalog import ActivityTypeRepository
from src.modules.storage.database import Database
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.errors import ConflictError
from src.modules.storage.owners import NO_OWNER
from src.modules.storage.users import UserRepository


class SheetImportError(ValueError):
    """Raised when a sheet cannot be imported; nothing is written."""


@dataclass
class ImportSummary:
    year: int
    replaced: bool = False
    days: Counter = field(default_factory=Counter)  # stored days by day type
    entries: Counter = field(default_factory=Counter)  # 'ticket', 'activity', 'zero', 'no ticket'
    corrected_tickets: int = 0
    unpaid_leave: int = 0
    flagged_entries: int = 0
    flagged_days: int = 0

    def lines(self) -> list[str]:
        types = ', '.join(f'{count} {day_type}' for day_type, count in sorted(self.days.items()) if day_type != 'work')
        return [
            f'Imported {self.year}' + (' (replaced existing data)' if self.replaced else ''),
            f'  Days:        {self.days.total()} stored ({types or "all work days"})',
            f'  Entries:     {self.entries["ticket"] + self.entries["activity"]} '
            f'({self.entries["ticket"]} ticket, {self.entries["activity"]} activity; '
            f'{self.entries["zero"]} at 0:00, {self.entries["no ticket"]} without ticket)',
            f'  Corrections: {self.corrected_tickets} ticket keys, {self.unpaid_leave} days of unpaid leave',
            f'  For review:  {self.flagged_entries} flagged entries, {self.flagged_days} flagged days',
        ]


def import_file(
    database: Database, path: str | Path, replace: bool = False, today: dt.date | None = None, login: str | None = None,
) -> tuple[ImportSummary, Reconciliation]:
    """Import a sheet into a user's data (`login`: username or e-mail address) and compare the result with it, in one
    transaction."""
    rows = read_sheet(path)
    database.migrate()
    with database.transaction() as conn:
        user_id = import_user(conn, login)
        summary = import_rows(conn, user_id, rows, replace)
        return summary, reconcile(conn, user_id, rows, today or dt.date.today())


def import_user(conn: sqlite3.Connection, login: str | None) -> str:
    """The given user; without one, the only user, or no owner yet while there is no user (the first user takes it)."""
    users = UserRepository(conn)
    if login:
        if (user := users.by_login(login)) is None:
            raise SheetImportError(f'No user {login!r}')
        return user.id
    if users.count() > 1:
        raise SheetImportError('Several users: name the one to import for with --user')
    return users.first_id() or NO_OWNER


def import_rows(
    conn: sqlite3.Connection, user_id: int, rows: Sequence[SheetRow], replace: bool = False,
    clock: Callable[[], dt.datetime] | None = None,
) -> ImportSummary:
    """Import the rows of one year into a user's data; refused if the year already holds data, unless `replace`."""
    year = _year_of(rows)
    summary = ImportSummary(year, replaced=_clear_year(conn, user_id, year, replace))
    importer = _YearImporter(conn, user_id, summary, clock)
    for row in rows:
        if imported := classify_day(row):
            importer.add(imported)
    return summary


def _year_of(rows: Sequence[SheetRow]) -> int:
    years = {row.date.year for row in rows}
    if len(years) != 1:
        raise SheetImportError(f'A sheet must hold exactly one year, found {sorted(years) or "no rows"}')
    return years.pop()


_YEAR_TABLES = ('days', 'entries', 'review_flags')


def _clear_year(conn: sqlite3.Connection, user_id: int, year: int, replace: bool) -> bool:
    """Delete the user's data of the year if `replace` is set; returns whether there was data. Tickets and services
    stay."""
    scope = (user_id, f'{year}-01-01', f'{year}-12-31')
    query = 'SELECT 1 FROM {} WHERE user_id = ? AND date BETWEEN ? AND ?'
    has_data = any(conn.execute(query.format(table), scope).fetchone() for table in _YEAR_TABLES)
    if has_data and not replace:
        raise ConflictError(f'{year} already holds data; import with replace to overwrite it')
    conn.execute('DELETE FROM entry_history WHERE entry_id IN '
                 '(SELECT id FROM entries WHERE user_id = ? AND date BETWEEN ? AND ?)', scope)
    for table in _YEAR_TABLES:
        conn.execute(f'DELETE FROM {table} WHERE user_id = ? AND date BETWEEN ? AND ?', scope)
    return has_data


class _YearImporter:
    def __init__(
        self, conn: sqlite3.Connection, user_id: int, summary: ImportSummary, clock: Callable[[], dt.datetime] | None,
    ) -> None:
        self._days = DayRepository(conn, user_id)
        self._entries = EntryRepository(conn, user_id, clock)
        self._activity_ids = {activity.name.lower(): activity.id for activity in ActivityTypeRepository(conn, user_id).all()}
        self._summary = summary

    def add(self, imported: ImportedDay) -> None:
        parsed = parse_comment(imported.lines)
        self._save_day(imported.day, parsed.notes)
        for flag in imported.flags:
            self._days.add_flag(flag.date, flag.reason, flag.detail)
            self._summary.flagged_days += 1
        for entry in parsed.entries:
            self._add_entry(imported.day.date, entry)

    def _save_day(self, day: Day, notes: Sequence[str]) -> None:
        """Store the day with its notes, unless it holds nothing (e.g. a weekend with placeholder times)."""
        day, corrected = correct_day(day)
        self._summary.unpaid_leave += corrected
        day = day.model_copy(update={'note': '\n'.join(filter(None, [day.note, *notes]))})
        if day.day_type or day.start is not None or day.note:
            self._days.save(day)
            self._summary.days[day.day_type or DayType.WORK] += 1

    def _add_entry(self, date: dt.date, parsed: ParsedEntry) -> None:
        created = self._entries.create(self._to_entry(date, parsed), HistoryAction.IMPORTED, parsed.source)
        if parsed.uncertain_ticket:
            self._entries.add_flag(created.id, FlagReason.UNCERTAIN_TICKET, parsed.source)
            self._summary.flagged_entries += 1
        self._count(parsed)

    def _to_entry(self, date: dt.date, parsed: ParsedEntry) -> Entry:
        try:
            if parsed.activity is None:
                return TicketEntry(
                    date=date, ticket_key=parsed.ticket_key, duration=parsed.duration,
                    description=parsed.text, coding=parsed.coding,
                )
            return ActivityEntry(
                date=date, activity_type_id=self._activity_id(parsed.activity), duration=parsed.duration, note=parsed.text
            )
        except ValidationError as error:
            raise SheetImportError(f'{date}: {parsed.source!r}: {error}') from error

    def _activity_id(self, name: str) -> int:
        if name.lower() not in self._activity_ids:
            raise SheetImportError(f'Activity type {name!r} does not exist')
        return self._activity_ids[name.lower()]

    def _count(self, parsed: ParsedEntry) -> None:
        self._summary.entries['activity' if parsed.activity else 'ticket'] += 1
        self._summary.entries['zero'] += parsed.duration == 0
        self._summary.entries['no ticket'] += parsed.activity is None and parsed.ticket_key is None
        self._summary.corrected_tickets += parsed.ticket_corrected
