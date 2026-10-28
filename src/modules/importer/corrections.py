"""Known corrections of the spreadsheet data that cannot be derived from the sheet itself."""

import datetime as dt

from src.lib.daytypes import DayType
from src.models.days import Day

# Marked "PTO" in the sheet, but unpaid leave.
UNPAID_LEAVE = frozenset({
    dt.date(2024, 8, 8),
    dt.date(2024, 8, 9),
    dt.date(2024, 10, 4),
    dt.date(2024, 12, 27),
    dt.date(2024, 12, 30),
})


def correct_day(day: Day) -> tuple[Day, bool]:
    """The corrected day and whether a correction was applied."""
    if day.date in UNPAID_LEAVE:
        return day.model_copy(update={'day_type': DayType.UNPAID_LEAVE}), True
    return day, False
