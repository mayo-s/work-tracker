"""Days and their review flags: the same behaviour on SQLite and on DynamoDB (moto)."""

import datetime as dt

import pytest

from src.lib.balances import DayRecord
from src.lib.daytypes import DayType
from src.lib.durations import parse_clock, parse_duration
from src.models.days import Day
from src.models.entries import ActivityEntry
from src.models.review import FlagReason
from src.modules.storage.errors import NotFoundError

MONDAY = dt.date(2026, 10, 26)
WORK_DAY = Day(date=MONDAY, start=parse_clock('08:15'), end=parse_clock('15:45'), note='ENGINE-597 europace permissions')


@pytest.fixture
def days(per_call, klara_id):
    return per_call(lambda store: store.days(klara_id))


def test_save_get_and_replace(days):
    assert days.get(MONDAY) is None
    days.save(WORK_DAY)
    assert days.get(MONDAY) == WORK_DAY
    pto = Day(date=MONDAY, day_type=DayType.PTO)
    days.save(pto)
    assert days.get(MONDAY) == pto


def test_save_keeps_empty_break_and_explicit_break(days):
    explicit = Day(date=MONDAY + dt.timedelta(days=1), start=parse_clock('07:30'), end=parse_clock('16:00'), break_minutes=0)
    days.save(WORK_DAY)
    days.save(explicit)
    assert days.get(MONDAY).break_minutes is None
    assert days.get(explicit.date).break_minutes == 0


def test_between_in_date_order(days):
    for offset in (3, 0, 1, 7):
        days.save(Day(date=MONDAY + dt.timedelta(days=offset), note=f'day {offset}'))
    found = days.between(MONDAY, MONDAY + dt.timedelta(days=6))
    assert [day.date for day in found] == [MONDAY, MONDAY + dt.timedelta(days=1), MONDAY + dt.timedelta(days=3)]


def test_records_for_balances(days):
    days.save(WORK_DAY)
    days.save(Day(date=MONDAY + dt.timedelta(days=1), day_type=DayType.PTO))
    assert days.records(MONDAY, MONDAY + dt.timedelta(days=6)) == {
        MONDAY: DayRecord(parse_duration('7:00'), None),
        MONDAY + dt.timedelta(days=1): DayRecord(0, DayType.PTO),
    }


def test_delete_day_and_its_flags(days):
    days.save(WORK_DAY)
    days.add_flag(MONDAY, FlagReason.WEEKEND_HOURS)
    days.delete(MONDAY)
    assert days.get(MONDAY) is None
    assert days.flags_on(MONDAY) == []


def test_missing_day_and_flag(days):
    with pytest.raises(NotFoundError):
        days.delete(MONDAY)
    with pytest.raises(NotFoundError):
        days.clear_flag(404)


def test_add_list_and_clear_flags(days):
    saturday = dt.date(2024, 11, 9)
    flag = days.add_flag(saturday, FlagReason.WEEKEND_HOURS, '5,0 Secretary - Holacracy Constitution')
    days.add_flag(dt.date(2024, 1, 6), FlagReason.WEEKEND_HOURS)
    assert days.flags_on(saturday) == [flag]
    assert [found.date for found in days.day_flags()] == [dt.date(2024, 1, 6), saturday]
    days.clear_flag(flag.id)
    assert days.flags_on(saturday) == []


def test_day_flags_ignore_entry_flags(days, per_call, klara_id, activity_type_ids):
    entries = per_call(lambda store: store.entries(klara_id))
    entry = entries.create(ActivityEntry(date=MONDAY, activity_type_id=activity_type_ids['Meeting'], duration=0))
    entries.add_flag(entry.id, FlagReason.UNCERTAIN_TICKET)
    assert days.day_flags() == []
