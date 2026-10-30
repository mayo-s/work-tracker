"""PTO years: the same behaviour on SQLite and on DynamoDB (moto)."""

from decimal import Decimal

import pytest

from src.lib.balances import PtoTerms
from src.models.pto import PtoYear
from src.modules.storage.errors import NotFoundError


@pytest.fixture
def years(per_call, klara_id, klara_pto_years):
    return per_call(lambda store: store.pto_years(klara_id))


def test_replace_all(years):
    years.replace_all([PtoYear(year=2027, allowance=Decimal(25)), PtoYear(year=2028, allowance=Decimal(30))])
    assert [(year.year, year.allowance) for year in years.all()] == [(2027, 25), (2028, 30)]


def test_save_inserts_and_replaces(years):
    changed = PtoYear(year=2026, allowance=Decimal(30), extra_days=Decimal(1), carried_over=Decimal(3), note='extra day')
    years.save(PtoYear(year=2030, allowance=Decimal(30)))
    years.save(changed)
    assert years.get(2026) == changed
    assert years.get(2030).carried_over is None


def test_get_missing_year(years):
    with pytest.raises(NotFoundError):
        years.get(2023)


def test_delete(years):
    years.delete(2027)
    assert 2027 not in years.terms()


def test_delete_missing_year(years):
    with pytest.raises(NotFoundError):
        years.delete(2023)


def test_terms(years):
    years.save(PtoYear(year=2026, allowance=Decimal(30), extra_days=Decimal(1), carried_over=Decimal(3)))
    assert years.terms()[2026] == PtoTerms(Decimal(30), Decimal(1), Decimal(3))


def test_carried_over_days_may_be_negative_and_halves(years):
    year = PtoYear(year=2026, allowance=Decimal('30.5'), carried_over=Decimal('-2.5'))
    years.save(year)
    assert years.get(2026) == year
