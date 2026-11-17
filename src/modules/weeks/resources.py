"""Week endpoint: /api/weeks/{week}, everything the week page shows in one answer (TASKS.md 14.3c); `member` shows a
member of the team admin's or auditor's team (team view, logged for the member)."""

import datetime as dt
from collections.abc import Callable

import falcon
from pydantic import BaseModel, Field
from spectree import Response

from src.models.catalog import ActivityType, ServiceChoice
from src.modules.days.resources import days_shown
from src.modules.days.schemas import DayView
from src.modules.entries.resources import entries_shown
from src.modules.entries.schemas import EntryView
from src.modules.reports.resources import monday_of
from src.modules.reports.schemas import Reports, WeekReport
from src.modules.storage.store import Storage
from src.modules.teams.view import MemberQuery, viewing
from src.utils.spec import spec


class WeekView(BaseModel):
    days: list[DayView] = Field(description='Monday to Sunday, recorded or not')
    entries: list[EntryView] = Field(description='By date and in the order they were created')
    report: WeekReport
    services: list[ServiceChoice] = Field(description="The services to choose in entries: the team's first, then the "
                                                      'personal ones; none in the team view, where nothing is edited')
    activity_types: list[ActivityType] = Field(description='The activity types to choose; none in the team view')


class WeekResource:
    def __init__(
        self, storage: Storage, today: Callable[[], dt.date] = dt.date.today,
        clock: Callable[[], dt.datetime] = dt.datetime.now,
    ) -> None:
        self._storage = storage
        self._today = today
        self._clock = clock

    @spec.validate(query=MemberQuery, resp=Response('HTTP_403', 'HTTP_404', HTTP_200=WeekView), tags=['Weeks'],
                   path_parameter_descriptions={'week': 'ISO week, e.g. 2026-W44'})
    def on_get(self, req: falcon.Request, resp: falcon.Response, week: str, query: MemberQuery) -> None:
        """A week (Monday to Sunday) as its page shows it: the days, the entries, the week's report and the lists to
        choose from. The same as `/api/days`, `/api/entries`, `/api/reports/weeks/{week}`, `/api/service-choices` and
        `/api/activity-types` answer one by one."""
        monday = monday_of(week)
        sunday = monday + dt.timedelta(days=6)
        with self._storage.transaction() as store:
            view = viewing(req, store, query.member, self._today())
            view.log(store, 'week', week, self._clock())
            resp.media = WeekView(
                days=days_shown(store, view, monday, sunday), entries=entries_shown(store, view, monday, sunday),
                report=Reports(store, view.user_id, self._today(), view.stays).week(week, monday),
                services=[] if view.team_view else store.services(view.user_id).choices(),
                activity_types=[] if view.team_view else store.activity_types(view.user_id).all())
