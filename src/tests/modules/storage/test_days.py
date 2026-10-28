import datetime as dt

import pytest

from src.lib.balances import DayRecord
from src.lib.daytypes import DayType
from src.lib.durations import parse_clock, parse_duration
from src.models.days import Day
from src.models.review import FlagReason
from src.modules.storage.days import DayRepository
from src.modules.storage.errors import NotFoundError

MONDAY = dt.date(2026, 10, 26)
WORK_DAY = Day(date=MONDAY, start=parse_clock('08:15'), end=parse_clock('15:45'), note='ENGINE-597 europace permissions')


@pytest.fixture
def days(conn):
    return DayRepository(conn)


def test_get_missing_day(days):
    assert days.get(MONDAY) is None


def test_save_and_get(days):
    days.save(WORK_DAY)
    assert days.get(MONDAY) == WORK_DAY


def test_save_keeps_empty_break_and_explicit_break(days):
    explicit = Day(date=MONDAY + dt.timedelta(days=1), start=parse_clock('07:30'), end=parse_clock('16:00'), break_minutes=0)
    days.save(WORK_DAY)
    days.save(explicit)
    assert days.get(MONDAY).break_minutes is None
    assert days.get(explicit.date).break_minutes == 0


def test_save_replaces_day(days):
    days.save(WORK_DAY)
    pto = Day(date=MONDAY, day_type=DayType.PTO)
    days.save(pto)
    assert days.get(MONDAY) == pto


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


def test_delete_missing_day(days):
    with pytest.raises(NotFoundError):
        days.delete(MONDAY)


def test_add_and_list_flags(days):
    saturday = dt.date(2024, 11, 9)
    flag = days.add_flag(saturday, FlagReason.WEEKEND_HOURS, '5,0 Secretary - Holacracy Constitution')
    days.add_flag(dt.date(2024, 1, 6), FlagReason.WEEKEND_HOURS)
    assert flag.id is not None
    assert days.flags_on(saturday) == [flag]
    assert [found.date for found in days.day_flags()] == [dt.date(2024, 1, 6), saturday]


def test_day_flags_ignore_entry_flags(days, conn):
    entry_id = conn.execute(
        "INSERT INTO entries (date, kind, activity_type_id, duration) VALUES ('2026-10-26', 'activity', 1, 0)"
    ).lastrowid
    conn.execute("INSERT INTO review_flags (entry_id, reason) VALUES (?, 'uncertain_ticket')", (entry_id,))
    assert days.day_flags() == []


def test_clear_flag(days):
    flag = days.add_flag(MONDAY, FlagReason.WEEKEND_HOURS)
    days.clear_flag(flag.id)
    assert days.flags_on(MONDAY) == []


def test_clear_missing_flag(days):
    with pytest.raises(NotFoundError):
        days.clear_flag(404)
