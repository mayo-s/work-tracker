"""The days of a member shown in the team view (SPEC 5.7): their stays in a team, each from the day they joined until
the day before they left. Days between stays, before the first and after the last are not shown."""

import datetime as dt
from dataclasses import dataclass

Period = tuple[dt.date, dt.date | None]  # joined on, left on (None: still in the team)


@dataclass(frozen=True)
class Stays:
    periods: tuple[Period, ...]

    @property
    def first(self) -> dt.date:
        """The first day shown."""
        return min(joined for joined, _ in self.periods)

    def shows(self, day: dt.date) -> bool:
        return any(joined <= day and (left is None or day < left) for joined, left in self.periods)
