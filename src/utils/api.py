"""Shared API types: dates in ISO format, clock times as HH:MM, durations as h:mm."""

import datetime as dt
from collections.abc import Callable
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, Field, ValidationError, model_validator

from src.lib.durations import format_clock, format_duration, parse_clock, parse_duration, parse_signed_duration

MAX_DAYS = 366

ClockText = Annotated[str, AfterValidator(lambda text: format_clock(parse_clock(text))), Field(examples=['08:15'])]
# Durations are read in all formats of parse_duration (1:30, 1.5, 1,5, 1h30m, 90m) and answered as h:mm
DurationText = Annotated[str, AfterValidator(lambda text: format_duration(parse_duration(text))), Field(examples=['1:30'])]
SignedDurationText = Annotated[
    str, AfterValidator(lambda text: format_duration(parse_signed_duration(text))), Field(examples=['12:30', '-1:45']),
]


class PeriodQuery(BaseModel):
    """Either a week (`2026-W44`) or a start and end date (inclusive, at most 366 days)."""

    week: str | None = Field(default=None, pattern=r'^\d{4}-W\d{2}$', examples=['2026-W44'])
    start: dt.date | None = None
    end: dt.date | None = None

    @model_validator(mode='after')
    def check_period(self) -> Self:
        if (self.week is None) == (self.start is None and self.end is None):
            raise ValueError('give either week, or start and end')
        start, end = self.period()
        if not 0 <= (end - start).days < MAX_DAYS:
            raise ValueError(f'end must be on or after start, at most {MAX_DAYS} days')
        return self

    def period(self) -> tuple[dt.date, dt.date]:
        if self.week:
            year, week = self.week.split('-W')
            monday = dt.date.fromisocalendar(int(year), int(week), 1)
            return monday, monday + dt.timedelta(days=6)
        if self.start is None or self.end is None:
            raise ValueError('start and end are both required')
        return self.start, self.end


def check_domain(build: Callable[[], object]) -> None:
    """Run a domain model check inside an API model validator, passing on only the messages.

    The domain model's own errors may contain values that cannot be shown as JSON (e.g. dates).
    """
    try:
        build()
    except ValidationError as error:
        raise ValueError('; '.join(detail['msg'].removeprefix('Value error, ') for detail in error.errors())) from None
