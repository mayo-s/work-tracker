"""Reading the yearly spreadsheet export (CSV): one row per calendar day."""

import csv
import datetime as dt
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from src.lib.durations import TimeFormatError, parse_clock, parse_duration

COLUMNS = ['Date', 'Start', 'End', 'Pause', 'Sum', 'Comment']
PLACEHOLDER_START = parse_clock('08:00')
PLACEHOLDER_END = parse_clock('16:00')
_WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


class SheetFormatError(ValueError):
    """Raised when the CSV does not match the expected spreadsheet layout."""


@dataclass(frozen=True)
class SheetRow:
    date: dt.date
    start: int | None
    end: int | None
    pause: int | None  # minutes; None when the cell is empty
    total: int  # the sheet's `Sum` in minutes
    comment: tuple[str, ...]  # non-empty comment lines, stripped

    @property
    def is_empty(self) -> bool:
        """No times and no comment, e.g. future days."""
        return self.start is None and not self.comment

    @property
    def has_placeholder_times(self) -> bool:
        """08:00–16:00 without a break: the sheet's filler for weekends, PTO and holidays (but also a possible work day)."""
        return (self.start, self.end) == (PLACEHOLDER_START, PLACEHOLDER_END) and not self.pause


def read_sheet(path: str | Path) -> list[SheetRow]:
    with open(path, encoding='utf-8-sig', newline='') as file:
        return list(parse_sheet(file))


def parse_sheet(lines: Iterator[str]) -> Iterator[SheetRow]:
    reader = csv.reader(lines)
    header = next(reader, None)
    if header != COLUMNS:
        raise SheetFormatError(f'Unexpected columns {header}, expected {COLUMNS}')
    for cells in reader:
        try:
            yield _parse_row(cells)
        except (ValueError, TimeFormatError) as error:
            raise SheetFormatError(f'Line {reader.line_num}: {error}') from error


def _parse_row(cells: list[str]) -> SheetRow:
    if len(cells) != len(COLUMNS):
        raise ValueError(f'expected {len(COLUMNS)} cells, got {len(cells)}')
    date, start, end, pause, total, comment = (cell.strip() for cell in cells)
    return SheetRow(
        date=_parse_date(date),
        start=_optional(start, parse_clock),
        end=_optional(end, parse_clock),
        pause=_optional(pause, int),
        total=parse_duration(total),
        comment=tuple(line.strip() for line in comment.splitlines() if line.strip()),
    )


def _optional[T](text: str, parse: Callable[[str], T]) -> T | None:
    return parse(text) if text else None


def _parse_date(text: str) -> dt.date:
    """`01.01.2026 Thu` → 2026-01-01; the weekday must match the date."""
    day, _, weekday = text.partition(' ')
    date = dt.datetime.strptime(day, '%d.%m.%Y').date()
    if weekday != _WEEKDAYS[date.weekday()]:
        raise ValueError(f'{text!r}: {day} is not a {weekday}')
    return date
