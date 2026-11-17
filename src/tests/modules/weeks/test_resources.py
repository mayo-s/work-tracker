import falcon

from src.tests.ids import CODING


def test_the_week_answers_what_its_five_single_calls_answer(client):
    """Days, entries, report, services and activity types of the week page in one call (TASKS.md 14.3c)."""
    client.simulate_put('/api/days/2026-10-28', json={'start': '08:00', 'end': '16:30'})
    client.simulate_post('/api/entries', json={'date': '2026-10-28', 'activity_type_id': CODING, 'duration': '1:30',
                                               'ticket_key': 'TNG-5882'})
    single = {'days': '/api/days?week=2026-W44', 'entries': '/api/entries?week=2026-W44',
              'report': '/api/reports/weeks/2026-W44', 'services': '/api/service-choices',
              'activity_types': '/api/activity-types'}
    week = client.simulate_get('/api/weeks/2026-W44').json
    assert week == {name: client.simulate_get(path).json for name, path in single.items()}
    assert (len(week['days']), week['entries'][0]['ticket_key'], week['report']['week']) == (7, 'TNG-5882', '2026-W44')


def test_an_unknown_week_is_not_found(client):
    result = client.simulate_get('/api/weeks/2026-W54')
    assert (result.status, result.json['description']) == (falcon.HTTP_404, 'Unknown week 2026-W54, expected e.g. 2026-W44')
