import logging

import pytest
from pydantic import ValidationError

from src.modules.userdata.schemas import UserData
from src.utils.spec import error_locations, log_response_errors, spec


def test_error_locations_leave_out_input_and_message():
    errors = [{'type': 'value_error', 'loc': ('data', 'work_schedules', 0, 'state'), 'msg': "Unknown federal state 'XX'",
               'input': 'XX'}, {'type': 'missing', 'loc': ('user',), 'msg': 'Field required', 'input': {}}]
    assert error_locations(errors) == 'data.work_schedules.0.state (value_error), user (missing)'


def test_a_refused_import_is_logged_without_the_data(client, caplog):
    file = {'format': 'work-tracker', 'version': 1, 'exported_at': 'yesterday', 'days': [{'note': 'sick: migraine'}]}
    with caplog.at_level(logging.ERROR):
        assert client.simulate_post('/api/setup/import', json={'data': file}).status_code == 422
    assert 'data.exported_at (datetime_from_date_parsing)' in caplog.text
    assert 'data.days.0.date (missing)' in caplog.text
    assert 'migraine' not in caplog.text and 'yesterday' not in caplog.text


def test_a_failed_response_is_logged_without_the_data(caplog):
    with pytest.raises(ValidationError) as invalid:
        UserData.model_validate({'format': 'work-tracker', 'version': 1, 'days': [{'note': 'sick: migraine'}]})
    with caplog.at_level(logging.ERROR):
        log_response_errors(None, None, invalid.value, None, spec.model_adapter)
    assert '500 Response Validation Error: exported_at (missing)' in caplog.text
    assert 'migraine' not in caplog.text
