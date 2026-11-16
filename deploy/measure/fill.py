"""Fills a test account through the API with records to measure with (README, "Measuring response times"): five
services, days off in 2026, and for every work day from FIRST_DAY to today its entries and times; today stays open.
The same records on every run (a fixed seed); after a failure run it again: days already recorded or holding entries
are skipped. Ends with what the writes took.

    WT_LOGIN=… WT_PASSWORD=… python3 deploy/measure/fill.py BASE_URL FIRST_DAY    # e.g. … 2026-03-02
"""

import datetime as dt
import random
import statistics
import sys
from collections import defaultdict

from client import App

SERVICES = {'API': 'api-gateway', 'WEB': 'web-frontend', 'ENGINE': 'rules-engine', 'AUTH': 'identity-service',
            'DATA': 'data-pipeline'}
UNASSIGNED = 'OPS'  # tickets left without a service: they show up in the review
DAYS_OFF = [  # booked as ranges (the app leaves out weekends and holidays)
    ('2026-04-07', '2026-04-10', 'pto', 'Easter holidays'), ('2026-05-15', '2026-05-15', 'pto', 'Bridge day'),
    ('2026-06-09', '2026-06-10', 'sick', ''), ('2026-07-20', '2026-07-31', 'pto', 'Summer holidays'),
    ('2026-09-04', '2026-09-04', 'overtime_off', ''), ('2026-09-22', '2026-09-22', 'sick', ''),
    ('2026-10-14', '2026-10-16', 'pto', ''), ('2026-12-21', '2026-12-23', 'pto', 'Christmas'),
    ('2026-12-28', '2026-12-30', 'pto', 'Christmas'),
]
HALF_SICK = dt.date(2026, 11, 5)
MEETINGS = ['Daily', 'Daily', 'Daily', 'Sprint planning', 'Retro', '1:1', 'Refinement', 'Architecture round']
CODING = ['Implementation', 'Tests', 'Review feedback', 'Bug fix', 'Refactoring', 'PR review', 'Deployment', 'Analysis']
OTHER = {'Planning': ['Sprint preparation', 'Estimation', 'Roadmap'], 'Documentation': ['README', 'Runbook', 'API docs'],
         'Other': ['Onboarding', 'Support request', 'Tooling']}


def clock(minutes: int) -> str:
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def duration(minutes: int) -> str:
    return f'{minutes // 60}:{minutes % 60:02d}'


def split(total: int, parts: int) -> list[int]:
    """`total` minutes in that many parts of at least 15 minutes, in quarter hours."""
    quarters = total // 15
    cuts = sorted(random.sample(range(1, quarters), parts - 1)) if parts > 1 else []
    return [15 * (end - start) for start, end in zip([0, *cuts], [*cuts, quarters])]


class Tickets:
    """Tickets in progress: each is worked on for a few days, then the next number of its prefix follows."""

    def __init__(self) -> None:
        self._numbers = {prefix: random.randint(100, 900) for prefix in [*SERVICES, UNASSIGNED]}
        self._open: list[tuple[str, int]] = []  # key, days left
        self.known: set[str] = set()

    def today(self) -> list[str]:
        self._open = [(key, left - 1) for key, left in self._open if left > 1]
        while len(self._open) < 3:
            prefix = UNASSIGNED if random.random() < 0.04 else random.choice(list(SERVICES))
            self._numbers[prefix] += random.randint(1, 7)
            self._open.append((f'{prefix}-{self._numbers[prefix]}', random.randint(1, 4)))
        return [key for key, _ in random.sample(self._open, random.randint(1, 3))]


class Filler:
    def __init__(self, app: App) -> None:
        self._app = app
        self._took: dict[str, list[float]] = defaultdict(list)  # ms per kind of write
        self._tickets = Tickets()
        self._types = {item['name']: item['id'] for item in app.call('GET', '/api/activity-types').data}
        self._services = {item['short_name']: item['id'] for item in app.call('GET', '/api/services').data}

    def _write(self, method: str, path: str, body: dict, kind: str | None = None) -> dict:
        answer = self._app.call(method, path, body)
        self._took[kind or f'{method} {path}'].append(answer.took)
        return answer.data

    def services(self) -> None:
        for short_name in SERVICES.keys() - self._services.keys():
            service = self._write('POST', '/api/services', {'short_name': short_name, 'name': SERVICES[short_name]})
            self._services[short_name] = service['id']

    def days(self, first: dt.date, today: dt.date) -> dict[str, dict]:
        """The days from the first one to today by date, with the days off booked."""
        views = self._app.call('GET', f'/api/days?start={first}&end={today}').data
        if any(day['day_type'] == 'pto' for day in views):
            return {day['date']: day for day in views}
        for start, end, day_type, note in DAYS_OFF:
            self._write('POST', '/api/days/range', {'start': start, 'end': end, 'day_type': day_type, 'note': note})
        return {day['date']: day for day in self._app.call('GET', f'/api/days?start={first}&end={today}').data}

    def filled(self, first: dt.date, today: dt.date) -> set[str]:
        """The dates that hold entries already."""
        return {entry['date'] for entry in self._app.call('GET', f'/api/entries?start={first}&end={today}').data}

    def _entry(self, date: dt.date, activity_type: str, minutes: int, description: str) -> dict:
        return {'date': date.isoformat(), 'activity_type_id': self._types[activity_type], 'duration': duration(minutes),
                'description': description}

    def _ticket_entry(self, date: dt.date, key: str, minutes: int) -> dict:
        """Work on a ticket; its first entry says the service, unless it is one of those left for the review."""
        entry = self._entry(date, 'Coding', minutes, random.choice(CODING)) | {'ticket_key': key}
        prefix = key.split('-')[0]
        if key not in self._tickets.known and prefix in self._services:
            entry['service_id'] = self._services[prefix]
        self._tickets.known.add(key)
        return entry

    def entries(self, date: dt.date, worked: int) -> list[dict]:
        """A meeting, sometimes another activity, and work on one to three tickets; not every minute accounted for."""
        meeting = random.choice([15, 15, 30, 30, 45, 60])
        entries = [self._entry(date, 'Meeting', meeting, random.choice(MEETINGS))]
        rest = worked - meeting - random.choice([0, 0, 0, 15, 30])
        if random.random() < 0.3 and rest > 120:
            name, minutes = random.choice(list(OTHER)), random.choice([30, 45, 60, 90])
            entries.append(self._entry(date, name, minutes, random.choice(OTHER[name])))
            rest -= minutes
        keys = self._tickets.today()
        return entries + [self._ticket_entry(date, key, minutes) for key, minutes in zip(keys, split(rest, len(keys)))]

    def record(self, date: dt.date, entries: list[dict], start: int, worked: int | None) -> None:
        """The day's entries and its times; without `worked`, the day stays open."""
        for entry in entries:
            self._write('POST', '/api/entries', entry)
        day = {'start': clock(start)}
        if worked is not None:
            day['end'] = clock(start + worked + (0 if worked <= 360 else 30 if worked <= 540 else 45))
        if date == HALF_SICK:
            day['day_type'] = 'sick_half'
        self._write('PUT', f'/api/days/{date}', day, 'PUT /api/days/{date}')

    def summary(self) -> str:
        lines = [f'{len(self._tickets.known)} tickets']
        for kind, took in sorted(self._took.items()):
            took.sort()
            lines.append(f'  {kind:20} n={len(took):4}  median {statistics.median(took):5.0f} ms  '
                         f'p90 {took[int(len(took) * 0.9)]:5.0f} ms  max {took[-1]:6.0f} ms')
        return '\n'.join(lines)


def workable(view: dict, filled: set[str]) -> bool:
    """A work day without a day type of its own, not recorded yet and without entries."""
    return (view['work_day'] and view['day_type'] == 'work' and view['automatic'] and not view['recorded']
            and view['date'] not in filled)


def drawn(filler: Filler, date: dt.date, today: dt.date) -> tuple[list[dict], int, int | None]:
    """A day's entries, its start and the minutes worked (none for today, which stays open); drawn for every date,
    also those skipped, so a rerun draws the same records."""
    start = random.choice(range(7 * 60 + 45, 9 * 60 + 30, 15))
    worked = 480 + random.choice([-60, -45, -30, -15, 0, 0, 0, 0, 15, 30, 30, 45, 60])
    worked = 240 if date == HALF_SICK else worked
    return filler.entries(date, 120 if date == today else worked), start, None if date == today else worked


def main(base_url: str, first_day: str) -> None:
    random.seed(20260301)
    first, today, filler = dt.date.fromisoformat(first_day), dt.date.today(), Filler(App(base_url))
    filler.services()
    views, filled = filler.days(first, today), filler.filled(first, today)
    count = 0
    for date in (first + dt.timedelta(days=offset) for offset in range((today - first).days + 1)):
        entries, start, worked = drawn(filler, date, today)
        if workable(views[date.isoformat()], filled):
            filler.record(date, entries, start, worked)
            count += 1
            print(f'  {date}: {len(entries)} entries', flush=True)
    print(f'Filled {count} days, {filler.summary()}')


if __name__ == '__main__':
    main(*sys.argv[1:3])
