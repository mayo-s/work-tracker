import datetime as dt

import pytest

from src.lib.public_holidays import Holiday, HolidayKind, HolidayRules, holiday_on, holidays_between

BERLIN_2025 = [
    dt.date(2025, 1, 1),
    dt.date(2025, 3, 8),
    dt.date(2025, 4, 18),
    dt.date(2025, 4, 21),
    dt.date(2025, 5, 1),
    dt.date(2025, 5, 8),
    dt.date(2025, 5, 29),
    dt.date(2025, 6, 9),
    dt.date(2025, 10, 3),
    dt.date(2025, 12, 25),
    dt.date(2025, 12, 26),
]


@pytest.mark.parametrize('date, name', [
    (dt.date(2024, 10, 3), 'German Unity Day'),
    (dt.date(2025, 4, 18), 'Good Friday'),
    (dt.date(2026, 3, 8), "Women's Day"),
    (dt.date(2026, 5, 14), 'Ascension Day'),
    (dt.date(2026, 12, 26), 'Second Day of Christmas'),
])
def test_public_holiday(date, name):
    assert holiday_on(date) == Holiday(date, name, HolidayKind.PUBLIC)


def test_one_off_holiday_2025():
    found = holiday_on(dt.date(2025, 5, 8))
    assert found.kind is HolidayKind.PUBLIC
    assert found.name.startswith('80th anniversary of the liberation')


@pytest.mark.parametrize('date', [
    dt.date(2026, 4, 5),
    dt.date(2026, 5, 8),
    dt.date(2025, 10, 31),
    dt.date(2026, 10, 27),
])
def test_no_holiday(date):
    assert holiday_on(date) is None


@pytest.mark.parametrize('date, name', [
    (dt.date(2025, 12, 24), 'Christmas Eve'),
    (dt.date(2025, 12, 31), "New Year's Eve"),
    (dt.date(2028, 12, 24), 'Christmas Eve'),
])
def test_company_half_day(date, name):
    assert holiday_on(date) == Holiday(date, name, HolidayKind.COMPANY_HALF_DAY)


def test_holidays_between_full_year():
    found = holidays_between(dt.date(2025, 1, 1), dt.date(2025, 12, 31))
    public = [holiday.date for holiday in found if holiday.kind is HolidayKind.PUBLIC]
    company = [holiday.date for holiday in found if holiday.kind is HolidayKind.COMPANY_HALF_DAY]
    assert public == BERLIN_2025
    assert company == [dt.date(2025, 12, 24), dt.date(2025, 12, 31)]


def test_holidays_between_across_years_in_order():
    found = holidays_between(dt.date(2025, 12, 20), dt.date(2026, 1, 6))
    assert [holiday.date for holiday in found] == [
        dt.date(2025, 12, 24),
        dt.date(2025, 12, 25),
        dt.date(2025, 12, 26),
        dt.date(2025, 12, 31),
        dt.date(2026, 1, 1),
    ]


def test_holidays_between_single_day():
    assert holidays_between(dt.date(2026, 10, 3), dt.date(2026, 10, 3)) == [holiday_on(dt.date(2026, 10, 3))]


def test_holidays_between_rejects_end_before_start():
    start, end = dt.date(2026, 2, 1), dt.date(2026, 1, 1)
    with pytest.raises(ValueError):
        holidays_between(start, end)


@pytest.mark.parametrize('state, date, name', [
    ('BY', dt.date(2027, 1, 6), 'Epiphany'),
    ('HH', dt.date(2026, 10, 31), 'Reformation Day'),
    ('NW', dt.date(2026, 6, 4), 'Corpus Christi'),
])
def test_public_holidays_of_other_states(state, date, name):
    assert holiday_on(date, HolidayRules(state)) == Holiday(date, name, HolidayKind.PUBLIC)


def test_womens_day_is_no_holiday_in_bavaria():
    assert holiday_on(dt.date(2026, 3, 8), HolidayRules('BY')) is None


def test_without_company_half_days():
    rules = HolidayRules('BE', company_half_days=False)
    assert holidays_between(dt.date(2025, 12, 20), dt.date(2025, 12, 31), rules) == [
        holiday_on(dt.date(2025, 12, 25)), holiday_on(dt.date(2025, 12, 26))]


@pytest.mark.parametrize('state', ['Berlin', 'Augsburg', 'XX', ''])
def test_rules_reject_unknown_states(state):
    with pytest.raises(ValueError):
        HolidayRules(state)
