import pytest

from src.models.former_entries import convert, ticket_activity_type


@pytest.mark.parametrize('coding, description, activity_type', [
    (True, 'europace', 'Coding'),
    (False, 'PR review zipkin', 'Coding'),
    (False, 'Refinement', 'Meeting'),
    (False, 'investigation', None),
])
def test_the_activity_type_of_a_former_ticket_entry(coding, description, activity_type):
    assert ticket_activity_type(coding, description) == activity_type


def test_convert_keeps_other_fields_and_adds_the_activity_type():
    ticket = {'SK': 'ENTRY#1', 'kind': 'ticket', 'ticket_key': 'TNG-1', 'description': 'europace', 'coding': True}
    activity = {'SK': 'ENTRY#2', 'kind': 'activity', 'activity_type_id': 'a1', 'note': 'Standup'}
    assert convert(ticket, lambda name: name.lower()) == {
        'SK': 'ENTRY#1', 'ticket_key': 'TNG-1', 'description': 'europace', 'activity_type_id': 'coding'}
    assert convert(activity, lambda name: name.lower()) == {
        'SK': 'ENTRY#2', 'activity_type_id': 'a1', 'ticket_key': None, 'description': 'Standup'}
