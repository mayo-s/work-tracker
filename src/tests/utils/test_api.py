import datetime as dt

import pytest
from pydantic import BaseModel, ValidationError, model_validator

from src.models.days import Day
from src.utils.api import ClockText, DurationText, PeriodQuery, SignedDurationText, check_domain


def test_period_query_allows_a_leap_year():
    assert PeriodQuery(start='2024-01-01', end='2024-12-31').period()[1] == dt.date(2024, 12, 31)


@pytest.mark.parametrize('query, period', [
    ({'week': '2026-W44'}, (dt.date(2026, 10, 26), dt.date(2026, 11, 1))),
    ({'week': '2026-W01'}, (dt.date(2025, 12, 29), dt.date(2026, 1, 4))),
    ({'start': '2026-10-01', 'end': '2026-10-31'}, (dt.date(2026, 10, 1), dt.date(2026, 10, 31))),
    ({'start': '2026-10-28', 'end': '2026-10-28'}, (dt.date(2026, 10, 28), dt.date(2026, 10, 28))),
])
def test_period_query_period(query, period):
    assert PeriodQuery(**query).period() == period


@pytest.mark.parametrize('query', [
    {},
    {'start': '2026-10-01'},
    {'week': '2026-W44', 'start': '2026-10-01', 'end': '2026-10-31'},
    {'week': '2026-44'},
    {'week': '2026-W54'},
    {'start': '2026-10-31', 'end': '2026-10-01'},
    {'start': '2025-01-01', 'end': '2026-01-02'},
])
def test_period_query_rejects_invalid(query):
    with pytest.raises(ValidationError):
        PeriodQuery(**query)


class Times(BaseModel):
    clock: ClockText
    duration: DurationText
    balance: SignedDurationText = '0:00'


def test_times_are_normalized():
    assert Times(clock='7:15', duration='01:30', balance='+12:30') == Times(clock='07:15', duration='1:30', balance='12:30')
    assert Times(clock='7:15', duration='01:30', balance='-01:45').balance == '-1:45'


@pytest.mark.parametrize('data', [{'clock': '24:00', 'duration': '1:30'}, {'clock': '08:00', 'duration': '1:5'}])
def test_times_reject_invalid(data):
    with pytest.raises(ValidationError):
        Times(**data)


class Checked(BaseModel):
    start: int

    @model_validator(mode='after')
    def check(self):
        check_domain(lambda: Day(date=dt.date(2026, 10, 28), start=self.start))
        return self


def test_check_domain_passes_on_messages_only():
    with pytest.raises(ValidationError, match='start and end must be set together') as error:
        Checked(start=480)
    assert 'datetime.date' not in str(error.value.errors())
