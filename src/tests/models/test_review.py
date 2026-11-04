import datetime as dt

import pytest
from pydantic import ValidationError

from src.models.review import FlagReason, ReviewFlag


@pytest.mark.parametrize('target', [{}, {'entry_id': 7, 'date': dt.date(2024, 11, 9)}])
def test_flag_needs_exactly_one_target(target):
    with pytest.raises(ValidationError):
        ReviewFlag(reason=FlagReason.WEEKEND_HOURS, **target)
