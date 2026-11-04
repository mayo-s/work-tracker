"""Our rules on top of the `holidays` package: the state, the company half days and the order; the dates and names of
the public holidays are the package's."""

import datetime as dt

import pytest

from src.lib.public_holidays import Holiday, HolidayKind, HolidayRules, holiday_on, holidays_between


def test_public_holiday_and_working_day():
    assert holiday_on(dt.date(2024, 10, 3)) == Holiday(dt.date(2024, 10, 3), 'German Unity Day', HolidayKind.PUBLIC)
    assert holiday_on(dt.date(2026, 10, 27)) is None


def test_company_half_days():
    assert holiday_on(dt.date(2025, 12, 31)) == Holiday(dt.date(2025, 12, 31), "New Year's Eve", HolidayKind.COMPANY_HALF_DAY)
    assert holiday_on(dt.date(2028, 12, 24)).kind is HolidayKind.COMPANY_HALF_DAY  # on a Sunday too


def test_holidays_between_across_years_in_order():
    found = holidays_between(dt.date(2025, 12, 20), dt.date(2026, 1, 6))
    assert [(holiday.date, holiday.kind) for holiday in found] == [
        (dt.date(2025, 12, 24), HolidayKind.COMPANY_HALF_DAY),
        (dt.date(2025, 12, 25), HolidayKind.PUBLIC),
        (dt.date(2025, 12, 26), HolidayKind.PUBLIC),
        (dt.date(2025, 12, 31), HolidayKind.COMPANY_HALF_DAY),
        (dt.date(2026, 1, 1), HolidayKind.PUBLIC),
    ]


def test_holidays_between_rejects_end_before_start():
    start, end = dt.date(2026, 2, 1), dt.date(2026, 1, 1)
    with pytest.raises(ValueError):
        holidays_between(start, end)


def test_the_state_of_the_rules_applies():
    assert holiday_on(dt.date(2027, 1, 6), HolidayRules('BY')).name == 'Epiphany'
    assert holiday_on(dt.date(2027, 1, 6)) is None  # not in Berlin


def test_without_company_half_days():
    rules = HolidayRules('BE', company_half_days=False)
    assert [holiday.date for holiday in holidays_between(dt.date(2025, 12, 20), dt.date(2025, 12, 31), rules)] == [
        dt.date(2025, 12, 25), dt.date(2025, 12, 26)]


@pytest.mark.parametrize('state', ['Berlin', 'XX', ''])
def test_rules_reject_unknown_states(state):
    with pytest.raises(ValueError):
        HolidayRules(state)
