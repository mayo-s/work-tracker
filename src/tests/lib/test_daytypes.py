import datetime as dt
from decimal import Decimal

import pytest

from src.lib.daytypes import DayType, automatic_day_type, is_weekend, summarize_day
from src.lib.durations import parse_duration
from src.lib.public_holidays import HolidayRules
from src.lib.schedules import WorkSchedule

MONDAY = dt.date(2026, 10, 26)
SATURDAY = dt.date(2026, 10, 24)


def signed_minutes(text):
    return -parse_duration(text[1:]) if text.startswith('-') else parse_duration(text)


@pytest.mark.parametrize('date, weekend', [
    (dt.date(2026, 10, 23), False),
    (SATURDAY, True),
    (dt.date(2026, 10, 25), True),
    (MONDAY, False),
])
def test_is_weekend(date, weekend):
    assert is_weekend(date) is weekend


@pytest.mark.parametrize('date, day_type', [
    (MONDAY, DayType.WORK),
    (SATURDAY, DayType.WORK),
    (dt.date(2026, 10, 3), DayType.PUBLIC_HOLIDAY),
    (dt.date(2025, 5, 8), DayType.PUBLIC_HOLIDAY),
    (dt.date(2025, 12, 24), DayType.COMPANY_HALF_DAY),
    (dt.date(2025, 12, 31), DayType.COMPANY_HALF_DAY),
])
def test_automatic_day_type(date, day_type):
    assert automatic_day_type(date) is day_type


@pytest.mark.parametrize('day_type, target, pto_days', [
    (DayType.WORK, '8:00', '0'),
    (DayType.PTO, '0:00', '1'),
    (DayType.PTO_HALF, '4:00', '0.5'),
    (DayType.SICK, '0:00', '0'),
    (DayType.SICK_HALF, '4:00', '0'),
    (DayType.OVERTIME_OFF, '8:00', '0'),
    (DayType.UNPAID_LEAVE, '0:00', '0'),
    (DayType.PUBLIC_HOLIDAY, '0:00', '0'),
    (DayType.COMPANY_HALF_DAY, '0:00', '0.5'),
])
def test_weekday_rules(day_type, target, pto_days):
    summary = summarize_day(MONDAY, day_type=day_type)
    assert summary.target == parse_duration(target)
    assert summary.pto_days == Decimal(pto_days)


@pytest.mark.parametrize('day_type', list(DayType))
def test_weekend_has_no_target_and_uses_no_pto(day_type):
    summary = summarize_day(SATURDAY, day_type=day_type)
    assert summary.target == 0
    assert summary.pto_days == 0


def test_automatic_type_applies_without_choice():
    summary = summarize_day(dt.date(2025, 12, 24))
    assert summary.day_type is DayType.COMPANY_HALF_DAY
    assert summary.pto_days == Decimal('0.5')


@pytest.mark.parametrize('date', [dt.date(2025, 10, 3), dt.date(2025, 12, 31)])
def test_chosen_type_overrides_holiday(date):
    summary = summarize_day(date, day_type=DayType.WORK)
    assert summary.day_type is DayType.WORK
    assert summary.target == parse_duration('8:00')
    assert summary.pto_days == 0


def test_company_half_day_on_weekend_uses_no_pto():
    summary = summarize_day(dt.date(2028, 12, 24))
    assert summary.day_type is DayType.COMPANY_HALF_DAY
    assert summary.pto_days == 0


@pytest.mark.parametrize('date, day_type, worked, overtime', [
    (MONDAY, None, '8:15', '0:15'),
    (MONDAY, None, '7:30', '-0:30'),
    (MONDAY, None, '0:00', '-8:00'),
    (SATURDAY, None, '3:30', '3:30'),
    (dt.date(2024, 6, 20), DayType.PTO_HALF, '4:45', '0:45'),
    (dt.date(2025, 1, 30), DayType.SICK_HALF, '4:00', '0:00'),
    (dt.date(2025, 5, 30), DayType.OVERTIME_OFF, '0:00', '-8:00'),
    (dt.date(2026, 7, 13), DayType.PTO, '0:00', '0:00'),
    (dt.date(2026, 10, 5), None, '8:00', '0:00'),
    (dt.date(2025, 5, 8), None, '2:00', '2:00'),
])
def test_overtime(date, day_type, worked, overtime):
    assert summarize_day(date, parse_duration(worked), day_type).overtime == signed_minutes(overtime)


def test_summarize_day_rejects_negative_worked():
    with pytest.raises(ValueError):
        summarize_day(MONDAY, -1)


FOUR_DAYS = WorkSchedule(dt.date(2027, 1, 1), 30 * 60, frozenset(range(1, 5)))  # 30 h, Monday to Thursday: 7:30 per day


@pytest.mark.parametrize('day_type, target', [(None, '7:30'), (DayType.PTO_HALF, '3:45'), (DayType.OVERTIME_OFF, '7:30')])
def test_target_follows_the_schedule(day_type, target):
    summary = summarize_day(dt.date(2027, 1, 7), day_type=day_type, schedule=FOUR_DAYS)
    assert (summary.target, summary.work_day) == (parse_duration(target), True)


def test_day_off_of_the_schedule_is_like_a_weekend():
    summary = summarize_day(dt.date(2027, 1, 8), parse_duration('2:00'), DayType.PTO, schedule=FOUR_DAYS)  # a Friday
    assert (summary.target, summary.pto_days, summary.overtime, summary.work_day) == (0, 0, 120, False)


def test_automatic_type_follows_the_holiday_rules_of_the_schedule():
    bavaria = WorkSchedule(dt.date(2027, 1, 1), 40 * 60, frozenset(range(1, 6)), HolidayRules('BY', company_half_days=False))
    assert summarize_day(dt.date(2027, 1, 6), schedule=bavaria).day_type is DayType.PUBLIC_HOLIDAY
    christmas_eve = summarize_day(dt.date(2027, 12, 24), schedule=bavaria)
    assert (christmas_eve.day_type, christmas_eve.target, christmas_eve.pto_days) == (DayType.WORK, 480, 0)
