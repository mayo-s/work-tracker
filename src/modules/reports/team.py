"""The team report (SPEC 5.12): a summary of the activities of a team for a month or a year, what work was done.

Only hours: no descriptions or notes, no days off, no running figures. Activity types and services belong to each user,
so the team's figures merge them by name.
"""

import csv
import datetime as dt
import io
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from typing import Self

from pydantic import BaseModel, Field, model_validator

from src.lib.durations import format_duration, parse_duration
from src.lib.texts import text
from src.models.teams import Team
from src.modules.pages.languages import in_request_language
from src.modules.reports.schemas import PeriodWork, Reports, month_bounds
from src.modules.storage.store import Store
from src.modules.teams.schemas import StayView
from src.modules.teams.view import TeamPerson, TeamScope


class TeamReportQuery(BaseModel):
    """Either a month or a year."""

    month: str | None = Field(default=None, pattern=r'^[1-9]\d{3}-(0[1-9]|1[0-2])$', examples=['2026-10'])
    year: int | None = Field(default=None, ge=1000, le=9999, examples=[2026])

    @model_validator(mode='after')
    def check_period(self) -> Self:
        if (self.month is None) == (self.year is None):
            raise ValueError('give either month or year')
        return self

    def period(self) -> tuple[dt.date, dt.date]:
        if self.month is None:
            return dt.date(self.year, 1, 1), dt.date(self.year, 12, 31)
        year, month = self.month.split('-')
        return month_bounds(int(year), int(month))


class ActivityHours(BaseModel):
    activity_type: str
    duration: str


class TicketHours(BaseModel):
    ticket_key: str | None = Field(description='Null for entries still without the ticket their activity type requires')
    duration: str


class TeamServiceHours(BaseModel):
    service: str | None = Field(description='Null for tickets without service')
    duration: str
    tickets: list[TicketHours] = Field(description='Most hours first')


class Hours(BaseModel):
    """On the days counted: up to today, and only the days in the team."""

    worked: str
    target: str
    overtime: str
    entries: str | None = Field(description='Hours in entries; null without any')


class MemberSummary(Hours):
    user_id: str
    name: str
    stays: list[StayView] = Field(description='Their stays in the team during the period, oldest first')
    note: str | None = Field(description='When they were in the team, e.g. `from 04.11.`; null if there all period')
    activity_types: list[ActivityHours] = Field(description='Most hours first')


MemberWork = tuple[MemberSummary, PeriodWork]
CsvRow = tuple[str, str, str, str]

_NOT_IN_FILE_NAME = re.compile(r'[^\w.-]+')
_CSV_HEADER = ('Section', 'Name', 'Figure', 'Duration')
_FORMULA_START = ('=', '+', '-', '@', '\t', '\r')
_CURRENT_ONLY_NOTE = ('Current members only, each from the day they joined: '
                      'the total of a past period shrinks when someone leaves.')


class TeamReport(BaseModel):
    team_id: str
    team: str
    start: dt.date
    end: dt.date
    until: dt.date | None = Field(description='Last day counted (today at the latest); null if nothing counted yet')
    current_members_only: bool = Field(
        description="A team admin's report: former members are left out, so a past period's total shrinks when one leaves")
    totals: Hours
    activity_types: list[ActivityHours] = Field(description='Merged by name, most hours first')
    services: list[TeamServiceHours] = Field(description='Merged by name, most hours first; tickets without service last')
    members: list[MemberSummary] = Field(description='Everyone counted in the period, by name')


def team_report(store: Store, team: Team, scope: TeamScope, start: dt.date, end: dt.date, today: dt.date) -> TeamReport:
    """The report of the people in `scope` who were in the team during the period, within the store's transaction."""
    summaries = _summaries(store, scope, start, end, today)
    members = [member for member, _ in summaries]
    works = [work for _, work in summaries]
    return TeamReport(
        team_id=team.id, team=team.name, start=start, end=end, until=min(end, today) if start <= today else None,
        current_members_only=scope.current_only, totals=_totals(members), activity_types=_activity_types(works),
        services=_services(works), members=members,
    )


def _summaries(store: Store, scope: TeamScope, start: dt.date, end: dt.date, today: dt.date) -> list[MemberWork]:
    """Everyone in the team during the period, by name."""
    summaries = [_member(store, person, start, end, today) for person in scope.people if person.stays.within(start, end)]
    return sorted(summaries, key=lambda summary: summary[0].name.lower())


def _member(store: Store, person: TeamPerson, start: dt.date, end: dt.date, today: dt.date) -> MemberWork:
    totals, work = Reports(store, person.user_id, today, person.stays).summary(start, end)
    stays = [StayView(joined_on=joined, left_on=left) for joined, left in person.stays.within(start, end)]
    return MemberSummary(
        user_id=person.user_id, name=store.users().get(person.user_id).full_name,
        stays=stays, note=stay_note(stays, start, end),
        worked=totals.worked, target=totals.target, overtime=totals.overtime,
        entries=_entries(parse_duration(work.total(min(end, today)))),
        activity_types=[ActivityHours(activity_type=item.activity_type, duration=item.duration)
                        for item in work.activity_types()],
    ), work


def stay_note(stays: list[StayView], start: dt.date, end: dt.date) -> str | None:
    """When someone was in the team, if not for the whole period, e.g. `from 04.11.` or `02.11.–03.11.`; None if they
    were there all period."""
    notes = (_stay_part(stay, start, end) for stay in stays)
    return ', '.join(note for note in notes if note) or None


def _stay_part(stay: StayView, start: dt.date, end: dt.date) -> str | None:
    joined, until = stay.joined_on if stay.joined_on > start else None, _last_day(stay, end)
    if joined and until:
        return f'{joined:%d.%m.}–{until:%d.%m.}'
    if joined:
        return in_request_language(text('from {date}', date=f'{joined:%d.%m.}'))
    return in_request_language(text('until {date}', date=f'{until:%d.%m.}')) if until else None


def _last_day(stay: StayView, end: dt.date) -> dt.date | None:
    """The last day in the team, if within the period: `left_on` is the first day no longer in it."""
    return stay.left_on - dt.timedelta(days=1) if stay.left_on and stay.left_on <= end else None


def _entries(minutes: int) -> str | None:
    return format_duration(minutes) if minutes else None


def _totals(members: list[MemberSummary]) -> Hours:
    worked = sum(parse_duration(member.worked) for member in members)
    target = sum(parse_duration(member.target) for member in members)
    return Hours(worked=format_duration(worked), target=format_duration(target), overtime=format_duration(worked - target),
                 entries=_entries(sum(parse_duration(member.entries or '0:00') for member in members)))


def _activity_types(works: list[PeriodWork]) -> list[ActivityHours]:
    hours = ((item.activity_type, parse_duration(item.duration)) for work in works for item in work.activity_types())
    merged = _merged_by_name(hours)
    return [ActivityHours(activity_type=name, duration=format_duration(minutes)) for name, minutes in merged]


def _merged_by_name(hours: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
    """The hours per name ignoring case, in its first spelling; most hours first, then by name."""
    spelling: dict[str, str] = {}
    minutes: Counter[str] = Counter()
    for name, duration in hours:
        minutes[spelling.setdefault(name.casefold(), name)] += duration
    return sorted(minutes.items(), key=lambda item: (-item[1], item[0].lower()))


def _services(works: list[PeriodWork]) -> list[TeamServiceHours]:
    views = [_service_hours(service, hours) for service, hours in _tickets_by_service(works).items()]
    return sorted(views, key=lambda view: (view.service is None, -parse_duration(view.duration), (view.service or '').lower()))


def _tickets_by_service(works: list[PeriodWork]) -> dict[str | None, Counter[str | None]]:
    """The minutes per ticket of each service, by its name ignoring case, in its first spelling."""
    spelling: dict[str | None, str | None] = {}
    tickets: defaultdict[str | None, Counter[str | None]] = defaultdict(Counter)
    for service in (service for work in works for service in work.services()):
        name = spelling.setdefault(service.service and service.service.casefold(), service.service)
        tickets[name].update({ticket.ticket_key: parse_duration(ticket.duration) for ticket in service.tickets})
    return tickets


def _service_hours(service: str | None, tickets: Counter[str | None]) -> TeamServiceHours:
    ordered = sorted(tickets.items(), key=lambda item: (-item[1], item[0] is None, item[0] or ''))
    return TeamServiceHours(service=service, duration=format_duration(sum(tickets.values())),
                            tickets=[TicketHours(ticket_key=key, duration=format_duration(minutes))
                                     for key, minutes in ordered])


def team_report_file_name(team: str, now: dt.datetime) -> str:
    """E.g. `20261109_1430_team_report_Platform`, without extension; other characters than letters, digits, `.` and `-`
    in the team's name become `_`."""
    name = _NOT_IN_FILE_NAME.sub('_', team).strip('_')
    return f'{now:%Y%m%d_%H%M}_team_report_{name}'


def team_report_csv(report: TeamReport) -> bytes:
    """The report as CSV, one row per figure: semicolons and a byte order mark, so German Excel opens it in columns with
    the umlauts intact."""
    text = io.StringIO(newline='')
    writer = csv.writer(text, delimiter=';', lineterminator='\r\n')
    writer.writerow(_CSV_HEADER)
    writer.writerows((section, _no_formula(name), _no_formula(figure), duration)
                     for section, name, figure, duration in _csv_rows(report))
    return text.getvalue().encode('utf-8-sig')


def _no_formula(text: str) -> str:
    """Names come from users; a spreadsheet must not run them. Durations come from the app, so `-2:00` stays a duration."""
    return f"'{text}" if text.startswith(_FORMULA_START) else text


def _csv_rows(report: TeamReport) -> Iterator[CsvRow]:
    yield from _team_rows(report)
    for item in report.activity_types:
        yield 'Activity type', item.activity_type, 'Total', item.duration
    for service in report.services:
        yield from _service_rows(service)
    for member in report.members:
        yield from _member_rows(member)


def _team_rows(report: TeamReport) -> Iterator[CsvRow]:
    yield 'Team', report.team, 'Period', f'{report.start:%d.%m.%Y}–{report.end:%d.%m.%Y}'
    if report.until and report.until < report.end:
        yield 'Team', report.team, 'Counted up to', f'{report.until:%d.%m.%Y}'
    if report.current_members_only:
        yield 'Team', report.team, 'Note', _CURRENT_ONLY_NOTE
    yield from _hours_rows('Team', report.team, report.totals)


def _member_rows(member: MemberSummary) -> Iterator[CsvRow]:
    if member.note:
        yield 'Member', member.name, 'Note', member.note
    yield from _hours_rows('Member', member.name, member)
    for item in member.activity_types:
        yield 'Member', member.name, item.activity_type, item.duration


def _hours_rows(section: str, name: str, hours: Hours) -> Iterator[CsvRow]:
    yield section, name, 'Worked', hours.worked
    yield section, name, 'Target', hours.target
    yield section, name, 'Overtime', hours.overtime
    yield section, name, 'Entries', hours.entries or ''


def _service_rows(service: TeamServiceHours) -> Iterator[CsvRow]:
    name = service.service or 'No service'
    yield 'Service', name, 'Total', service.duration
    for ticket in service.tickets:
        yield 'Service', name, ticket.ticket_key or 'No ticket', ticket.duration
