"""The imprint (SPEC 5.13): open to everyone, its details from $WORK_TRACKER_IMPRINT here (the SSM parameter on AWS
Lambda: test_stages)."""

import json
import logging

import falcon
import pytest
from falcon import testing

from src.app import create_app

DETAILS = {'name': 'Klara Himmel', 'street': 'Musterstraße 1', 'city': '10115 Berlin', 'country': 'Deutschland',
           'email': 'klara.himmel@example.com'}


@pytest.fixture(autouse=True)
def no_imprint(monkeypatch):
    """No imprint from .env, unless a test sets one."""
    monkeypatch.delenv('WORK_TRACKER_IMPRINT', raising=False)


def test_visitors_see_the_imprint_before_the_setup(fresh_database, monkeypatch):
    monkeypatch.setenv('WORK_TRACKER_IMPRINT', json.dumps(DETAILS))
    app = testing.TestClient(create_app(fresh_database, auth=True))
    page, details = app.simulate_get('/imprint'), app.simulate_get('/api/imprint')
    assert (page.status, 'data-page="imprint"' in page.text) == (falcon.HTTP_200, True)
    assert (details.status, details.json) == (falcon.HTTP_200, DETAILS)


@pytest.mark.parametrize('value, logged', [
    (None, 'The imprint is not configured: no imprint in $WORK_TRACKER_IMPRINT'),
    (json.dumps(DETAILS | {'street': ' '}), 'The imprint is not configured: street (string_too_short) in '
                                            '$WORK_TRACKER_IMPRINT'),
    ('Klara Himmel', 'The imprint is not configured:  (json_invalid) in $WORK_TRACKER_IMPRINT'),
])
def test_without_valid_details_the_imprint_is_not_configured(client, monkeypatch, caplog, value, logged):
    if value is not None:
        monkeypatch.setenv('WORK_TRACKER_IMPRINT', value)
    with caplog.at_level(logging.ERROR):
        result = client.simulate_get('/api/imprint')
    assert (result.status, result.json['description']) == (falcon.HTTP_404, 'The imprint is not configured')
    assert (caplog.messages, 'Klara' in caplog.text) == ([logged], False)
