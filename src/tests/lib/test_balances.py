import datetime as dt
from decimal import Decimal

from src.lib.balances import DayRecord, PtoTerms, overtime_balance, pto_accounts, summarize_period
from src.lib.dates import each_day
from src.lib.daytypes import DayType
from src.lib.durations import parse_duration

BALANCE_START = dt.date(2024, 6, 1)
TERMS = {2024: PtoTerms(Decimal(18)), 2025: PtoTerms(Decimal(30)), 2026: PtoTerms(Decimal(30))}


def worked(text):
    return DayRecord(parse_duration(text))


def full_pto(start, end):
    return {day: DayRecord(day_type=DayType.PTO) for day in each_day(start, end)}


def test_summarize_period_covers_every_calendar_day():
    days = summarize_period({}, dt.date(2026, 10, 19), dt.date(2026, 10, 25))
    assert [day.date for day in days] == list(each_day(dt.date(2026, 10, 19), dt.date(2026, 10, 25)))


def test_overtime_balance_of_a_week():
    records = {
        dt.date(2026, 10, 19): worked('8:00'),
        dt.date(2026, 10, 20): DayRecord(day_type=DayType.PTO),
        dt.date(2026, 10, 21): worked('9:00'),
        dt.date(2026, 10, 22): worked('8:15'),
        dt.date(2026, 10, 23): worked('7:30'),
        dt.date(2026, 10, 24): worked('1:00'),
    }
    assert overtime_balance(records, dt.date(2026, 10, 19), dt.date(2026, 10, 25)) == parse_duration('1:45')


def test_overtime_balance_counts_missing_weekday_as_nothing_worked():
    assert overtime_balance({}, dt.date(2026, 10, 26), dt.date(2026, 10, 26)) == -parse_duration('8:00')


def test_overtime_balance_ignores_missing_weekends_and_holidays():
    assert overtime_balance({}, dt.date(2025, 12, 24), dt.date(2025, 12, 28)) == 0


def test_overtime_balance_adds_opening_balance():
    records = {dt.date(2026, 10, 26): worked('9:00')}
    assert overtime_balance(records, dt.date(2026, 10, 26), dt.date(2026, 10, 26), opening=90) == 150


def test_overtime_balance_stops_at_until():
    records = {dt.date(2026, 10, 26): worked('9:00'), dt.date(2026, 10, 27): worked('6:30')}
    assert overtime_balance(records, dt.date(2026, 10, 26), dt.date(2026, 10, 26)) == 60


def test_overtime_balance_until_before_start_is_opening():
    assert overtime_balance({}, BALANCE_START, BALANCE_START - dt.timedelta(days=1), opening=30) == 30


def pto_2024():
    """PTO, unpaid leave and sick days of 2024 as in the spreadsheet (Heiligabend / Silvester are automatic)."""
    records = {
        dt.date(2024, 6, 20): DayRecord(parse_duration('4:45'), DayType.PTO_HALF),
        dt.date(2024, 6, 21): DayRecord(day_type=DayType.PTO),
        dt.date(2024, 10, 4): DayRecord(day_type=DayType.UNPAID_LEAVE),
        dt.date(2024, 10, 28): DayRecord(day_type=DayType.SICK),
        dt.date(2024, 11, 1): DayRecord(parse_duration('4:00'), DayType.PTO_HALF),
        dt.date(2024, 12, 20): DayRecord(parse_duration('4:00'), DayType.PTO_HALF),
        dt.date(2024, 12, 23): DayRecord(day_type=DayType.PTO),
        dt.date(2024, 12, 27): DayRecord(day_type=DayType.UNPAID_LEAVE),
        dt.date(2024, 12, 30): DayRecord(day_type=DayType.UNPAID_LEAVE),
    }
    records |= full_pto(dt.date(2024, 7, 22), dt.date(2024, 8, 7))
    records |= {day: DayRecord(day_type=DayType.UNPAID_LEAVE) for day in (dt.date(2024, 8, 8), dt.date(2024, 8, 9))}
    return records


def test_pto_remainder_is_carried_into_the_next_year():
    accounts = pto_accounts(pto_2024(), TERMS, BALANCE_START, dt.date(2025, 1, 31))
    assert [account.year for account in accounts] == [2024, 2025]
    assert accounts[0].used == Decimal('17.5')
    assert accounts[0].remaining == Decimal('0.5')
    assert accounts[1].carried_over == Decimal('0.5')


def test_pto_accounts_split_used_and_planned():
    records = full_pto(dt.date(2026, 7, 13), dt.date(2026, 7, 17)) | full_pto(dt.date(2026, 12, 28), dt.date(2026, 12, 30))
    account = pto_accounts(records, TERMS, dt.date(2026, 1, 1), dt.date(2026, 10, 27))[0]
    assert account.used == Decimal(5)
    assert account.planned == Decimal(4)
    assert account.remaining == Decimal(21)


def test_pto_accounts_carry_over_negative_remainder():
    # 25 weekdays of PTO plus the automatic half days on Heiligabend and Silvester: 18 - 26 = -8
    accounts = pto_accounts(full_pto(dt.date(2024, 6, 3), dt.date(2024, 7, 5)), TERMS, BALANCE_START, dt.date(2025, 1, 1))
    assert accounts[0].remaining == Decimal(-8)
    assert accounts[1].carried_over == Decimal(-8)


def test_pto_accounts_ignore_days_before_start():
    records = full_pto(dt.date(2024, 5, 27), dt.date(2024, 5, 31))
    account = pto_accounts(records, TERMS, BALANCE_START, dt.date(2024, 12, 31))[0]
    assert account.used == Decimal(1)


def test_pto_accounts_add_extra_days():
    terms = {2026: PtoTerms(Decimal(30), extra_days=Decimal(1))}
    account = pto_accounts(full_pto(dt.date(2026, 7, 13), dt.date(2026, 7, 17)), terms, dt.date(2026, 1, 1),
                           dt.date(2026, 10, 27))[0]
    assert (account.extra_days, account.remaining) == (Decimal(1), Decimal(25))  # 30 + 1 − 5 − 2 × 0.5 planned


def test_fixed_carry_over_replaces_the_remainder_and_later_years_build_on_it():
    terms = TERMS | {2025: PtoTerms(Decimal(30), carried_over=Decimal(3))}
    accounts = pto_accounts(pto_2024(), terms, BALANCE_START, dt.date(2026, 1, 31))
    assert [account.carried_over for account in accounts] == [Decimal(0), Decimal(3), Decimal(32)]  # 3 + 30 − 1


def test_year_without_terms_has_no_account():
    accounts = pto_accounts({}, {2026: PtoTerms(Decimal(30))}, dt.date(2025, 1, 1), dt.date(2026, 1, 31))
    assert accounts == []  # 2025 has no terms, so the remainder carried into 2026 is unknown


def test_fixed_carry_over_starts_an_account_after_a_year_without_terms():
    terms = {2026: PtoTerms(Decimal(30), carried_over=Decimal(3))}
    accounts = pto_accounts({}, terms, dt.date(2025, 1, 1), dt.date(2026, 1, 31))
    assert [(account.year, account.carried_over) for account in accounts] == [(2026, Decimal(3))]
