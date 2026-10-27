import datetime as dt

import pytest
from pydantic import ValidationError

from src.models.review import FlagReason, ReviewFlag


def test_entry_flag():
    flag = ReviewFlag(entry_id=7, reason=FlagReason.UNCERTAIN_TICKET, detail='#4347 aka #1482')
    assert flag.date is None


def test_day_flag():
    flag = ReviewFlag(date=dt.date(2024, 11, 9), reason='weekend_hours', detail='5,0 Secretary - Holacracy Constitution')
    assert flag.reason is FlagReason.WEEKEND_HOURS


@pytest.mark.parametrize('target', [{}, {'entry_id': 7, 'date': dt.date(2024, 11, 9)}])
def test_flag_needs_exactly_one_target(target):
    with pytest.raises(ValidationError):
        ReviewFlag(reason=FlagReason.WEEKEND_HOURS, **target)


def test_flag_rejects_unknown_reason():
    with pytest.raises(ValidationError):
        ReviewFlag(entry_id=7, reason='no_service')
