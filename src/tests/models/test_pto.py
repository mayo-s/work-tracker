from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.models.pto import PtoYear


@pytest.mark.parametrize('field, days', [('allowance', '-1'), ('allowance', '17.25'), ('extra_days', '-0.5')])
def test_reject_invalid_days(field, days):
    values = {'year': 2026, 'allowance': Decimal(30), field: Decimal(days)}
    with pytest.raises(ValidationError):
        PtoYear(**values)


def test_negative_fixed_carry_over_is_allowed():
    assert PtoYear(year=2026, allowance=Decimal(30), carried_over=Decimal('-2.5')).carried_over == Decimal('-2.5')
