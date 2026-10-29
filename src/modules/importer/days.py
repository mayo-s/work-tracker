"""Turning a spreadsheet row into a day: day type, working times, note and review flags.

The sheet counts `Sum` − 8:00 as overtime on every calendar day and fills weekends, PTO and
holidays with 08:00–16:00. The rules below keep the sheet's overtime while storing real times.
"""

import re
from dataclasses import dataclass
from typing import NamedTuple

from src.lib.daytypes import DayType, automatic_day_type, is_weekend
from src.lib.durations import format_clock, format_duration
from src.models.days import Day
from src.models.review import FlagReason, ReviewFlag
from src.modules.importer.lines import split_hours
from src.modules.importer.sheet import SheetRow

_SICK = re.compile(r'(?:PTO \()?off sick\b', re.IGNORECASE)
_PTO = re.compile(r'PTO\b', re.IGNORECASE)
SHEET_DAY = 8 * 60  # the spreadsheet's daily target: overtime is `Sum` − 8:00 on every day
_SHEET_HALF_DAY = SHEET_DAY // 2
_HALF_DAY_MARKERS = {_SHEET_HALF_DAY, 30}  # '4,0 PTO' (hours) or '0,5 PTO' (days)
_FULL_DAY_TYPES = {DayType.PTO, DayType.SICK, DayType.OVERTIME_OFF}


@dataclass(frozen=True)
class ImportedDay:
    day: Day
    lines: tuple[str, ...]  # comment lines left for task entries and the day note
    flags: tuple[ReviewFlag, ...] = ()


class _Absence(NamedTuple):
    sick: bool
    minutes: int | None  # leading hours of the line, if any


def classify_day(row: SheetRow) -> ImportedDay | None:
    """The day of a sheet row; None for empty (future) rows."""
    if row.is_empty:
        return None
    if is_weekend(row.date) or automatic_day_type(row.date) is not DayType.WORK:
        return _day_off(row)
    return _weekday(row)


def _absence(line: str) -> _Absence | None:
    minutes, rest = split_hours(line)
    if _SICK.match(rest):
        return _Absence(True, minutes)
    if _PTO.match(rest):
        return _Absence(False, minutes)
    return None


def _day_off(row: SheetRow) -> ImportedDay:
    """Weekend or holiday: target 0, so the sheet's overtime (`Sum` − 8:00) is the worked time."""
    lines = _day_off_lines(row)
    day = _day_off_times(row)
    return ImportedDay(day, lines, _weekend_flags(row, day.worked, lines))


def _has_hours(line: str) -> bool:
    return split_hours(line)[0] is not None


def _day_off_lines(row: SheetRow) -> tuple[str, ...]:
    """PTO lines are dropped (Heiligabend / Silvester are half PTO automatically), on holidays also the holiday name."""
    lines = [line for line in row.comment if not _absence(line)]
    if is_weekend(row.date):
        return tuple(lines)
    return tuple(line for line in lines if _has_hours(line))


def _day_off_times(row: SheetRow) -> Day:
    worked = max(row.total - SHEET_DAY, 0) if row.start is not None else 0
    if not worked:
        return Day(date=row.date)
    return Day(date=row.date, start=row.start, end=row.start + worked, break_minutes=0)


def _weekend_flags(row: SheetRow, worked: int, lines: tuple[str, ...]) -> tuple[ReviewFlag, ...]:
    """Weekend days with worked time or hours in the comment are flagged for review."""
    if not is_weekend(row.date) or not (worked or any(_has_hours(line) for line in lines)):
        return ()
    return (ReviewFlag(date=row.date, reason=FlagReason.WEEKEND_HOURS, detail=_describe(row)),)


def _weekday(row: SheetRow) -> ImportedDay:
    day_type, half_day, notes = None, False, []
    for line in row.comment:
        if (absence := _absence(line)) is None:
            continue
        found = _absence_type(absence, row)
        if found is None:
            notes.append(line)  # e.g. '2,0 PTO Zahnarzt': a reminder of overtime used
        else:
            day_type, half_day = found, found in (DayType.PTO_HALF, DayType.SICK_HALF)
    lines = tuple(line for line in row.comment if not _absence(line))
    return ImportedDay(_weekday_times(row, day_type, half_day).model_copy(update={'note': '\n'.join(notes)}), lines)


def _absence_type(absence: _Absence, row: SheetRow) -> DayType | None:
    """Full or half day of PTO or sickness; None for other hours (overtime used, not a day type)."""
    if absence.minutes in (None, SHEET_DAY):
        return _full_day_type(absence, row)
    if absence.minutes in _HALF_DAY_MARKERS and row.total >= SHEET_DAY:
        return DayType.SICK_HALF if absence.sick else DayType.PTO_HALF
    return None


def _full_day_type(absence: _Absence, row: SheetRow) -> DayType:
    """'PTO' with times but `Sum` 0:00 is a day off taken from the overtime balance (e.g. 30.05.2025)."""
    if absence.sick:
        return DayType.SICK
    return DayType.OVERTIME_OFF if row.start is not None and row.total == 0 else DayType.PTO


def _weekday_times(row: SheetRow, day_type: DayType | None, half_day: bool) -> Day:
    """Times of a weekday: none on full days off; on half days the sheet extended the end by 4:00."""
    if day_type in _FULL_DAY_TYPES or row.start is None:
        return Day(date=row.date, day_type=day_type)
    end = row.end - _SHEET_HALF_DAY if half_day else row.end
    return Day(date=row.date, day_type=day_type, start=row.start, end=end, break_minutes=row.pause or 0)


def _describe(row: SheetRow) -> str:
    """The original sheet values, e.g. '08:00–19:30, Sum 11:30: 3,5 ABREISE Lübeck'."""
    times = f'{format_clock(row.start)}–{format_clock(row.end)}, ' if row.start is not None else ''
    return f'{times}Sum {format_duration(row.total)}: {" | ".join(row.comment)}'[:500]
