"""Times every request of the dashboard, week, month and year page, one after the other on one connection, so on a
warm instance (README, "Measuring response times"): the median of RUNS calls each (default 7), as seen from here and,
on a stage with WORK_TRACKER_TIMING=on, as the app says (in the app, of it waiting for DynamoDB, calls and items).

    WT_LOGIN=… WT_PASSWORD=… python3 deploy/measure/calls.py BASE_URL [RUNS]
"""

import datetime as dt
import statistics
import sys

from client import Answer, App


def pages(today: dt.date) -> dict[str, list[str]]:
    """What each page requests, for the week, month and year of today."""
    year, week, _ = today.isocalendar()
    week, month = f'{year}-W{week:02d}', f'{today:%Y-%m}'
    return {
        'every page but the dashboard': ['/api/review/counts'],
        'dashboard': ['/', '/api/dashboard', '/api/audits'],
        'week': ['/week', f'/api/weeks/{week}'],
        'month': ['/month', f'/api/reports/months/{month}'],
        'year': ['/year', f'/api/reports/years/{today.year}'],
        'other': ['/api/review', '/api/tickets', '/api/auth/status'],
    }


def median(name: str, answers: list[Answer]) -> float:
    return statistics.median(answer.timing.get(name, 0) for answer in answers)


def line(path: str, answers: list[Answer]) -> str:
    took, size = [answer.took for answer in answers], answers[0].size / 1024
    text = f'  {path:34} {statistics.median(took):5.0f} ms  ({min(took):.0f}–{max(took):.0f})  {size:5.1f} kB'
    if 'app' in answers[0].timing:
        text += f'   app {median("app", answers):4.0f} ms'
    if 'db' in answers[0].timing:
        text += (f', of it DynamoDB {median("db", answers):4.0f} ms: {median("calls", answers):.0f} calls, '
                 f'{median("items", answers):.0f} items')
    return text


def main(base_url: str, runs: int = 7) -> None:
    app = App(base_url)
    for page, paths in pages(dt.date.today()).items():
        print(page)
        for path in paths:
            print(line(path, [app.call('GET', path) for _ in range(runs)]), flush=True)


if __name__ == '__main__':
    main(sys.argv[1], *map(int, sys.argv[2:3]))
