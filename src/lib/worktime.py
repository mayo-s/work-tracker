"""Presence, legal break and worked time of a day, all in minutes."""

SIX_HOURS = 6 * 60
NINE_HOURS = 9 * 60
SHORT_BREAK = 30
LONG_BREAK = 45


def presence_time(start: int, end: int) -> int:
    """Minutes between start and end (minutes since midnight); a day cannot pass midnight."""
    if end < start:
        raise ValueError(f'End {end} is before start {start}')
    return end - start


def legal_break(presence: int) -> int:
    """Minimum break by German ArbZG §4: 30 min beyond 6 h and 45 min beyond 9 h of work.

    Near the limits the break grows minute by minute, so the worked time never exceeds
    6:00 or 9:00 without the required break (e.g. presence 6:15 → break 0:15, worked 6:00).
    """
    if presence < 0:
        raise ValueError('presence must not be negative')
    if presence <= SIX_HOURS:
        return 0
    if presence <= NINE_HOURS + SHORT_BREAK:
        return min(presence - SIX_HOURS, SHORT_BREAK)
    return min(presence - NINE_HOURS, LONG_BREAK)


def worked_time(start: int, end: int, break_minutes: int | None = None) -> int:
    """Worked minutes = presence − break; without a break the legal minimum applies."""
    presence = presence_time(start, end)
    if break_minutes is None:
        break_minutes = legal_break(presence)
    if not 0 <= break_minutes <= presence:
        raise ValueError(f'Break {break_minutes} must be between 0 and the presence time {presence}')
    return presence - break_minutes
