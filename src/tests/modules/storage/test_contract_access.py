"""A user's repositories know only their own records (SPEC 7.3): another user's ids are unknown, on SQLite (by
`user_id`) and on DynamoDB (by partition) alike."""

import datetime as dt

import pytest

from src.models.catalog import ActivityType, Service
from src.models.entries import ActivityEntry, TicketEntry
from src.models.review import FlagReason
from src.models.teams import Team
from src.modules.storage.errors import ConflictError, NotFoundError
from src.tests.users import HANS, PASSWORD

MONDAY = dt.date(2026, 10, 26)


@pytest.fixture
def hans(storage, klara_id):
    with storage.transaction() as store:
        return store.users().add(HANS, PASSWORD).id


@pytest.fixture
def klaras(storage, klara_id, klara_schedule, klara_pto_years, service_ids, activity_type_ids):
    """One of Klara's records of each kind, and an invitation for Klara to a team."""
    with storage.transaction() as store:
        entries = store.entries(klara_id)
        entry = entries.create(TicketEntry(date=MONDAY, ticket_key='TNG-4138', duration=60, description='secret'))
        team = store.teams().add(Team(name='Platform'))
        store.invitations().invite(team.id, 'klara.himmel@example.com', klara_id)
        return {
            'entry': entry, 'entry_flag': entries.add_flag(entry.id, FlagReason.UNCERTAIN_TICKET),
            'day_flag': store.days(klara_id).add_flag(MONDAY, FlagReason.WEEKEND_HOURS), 'schedule': klara_schedule,
            'service': store.services(klara_id).get(service_ids['MSB']),
            'activity_type': store.activity_types(klara_id).get(activity_type_ids['Meeting']),
            'invitation': store.invitations().of_user(klara_id)[0],
        }


# What Hans tries with Klara's ids (`k`: Klara's records), and what the attempt gives
ATTEMPTS = {
    'get the entry': (lambda store, k, hans: store.entries(hans).get(k['entry'].id), NotFoundError),
    'change the entry': (lambda store, k, hans: store.entries(hans).update(k['entry'].model_copy(
        update={'description': 'mine'})), NotFoundError),
    'delete the entry': (lambda store, k, hans: store.entries(hans).delete(k['entry'].id), NotFoundError),
    'split the entry': (lambda store, k, hans: store.entries(hans).split(k['entry'].id, ['TNG-1', 'TNG-2']), NotFoundError),
    'flag the entry': (lambda store, k, hans: store.entries(hans).add_flag(k['entry'].id, FlagReason.UNCERTAIN_TICKET),
                       ConflictError),
    'clear the entry flag': (lambda store, k, hans: store.entries(hans).clear_flag(k['entry_flag'].id), NotFoundError),
    'clear the day flag': (lambda store, k, hans: store.days(hans).clear_flag(k['day_flag'].id), NotFoundError),
    'delete the day': (lambda store, k, hans: store.days(hans).delete(MONDAY), NotFoundError),
    'get the service': (lambda store, k, hans: store.services(hans).get(k['service'].id), NotFoundError),
    'change the service': (lambda store, k, hans: store.services(hans).update(
        Service(id=k['service'].id, short_name='MINE')), NotFoundError),
    'delete the service': (lambda store, k, hans: store.services(hans).delete(k['service'].id), NotFoundError),
    'get the activity type': (lambda store, k, hans: store.activity_types(hans).get(k['activity_type'].id), NotFoundError),
    'change the activity type': (lambda store, k, hans: store.activity_types(hans).update(
        ActivityType(id=k['activity_type'].id, name='Mine')), NotFoundError),
    'delete the activity type': (lambda store, k, hans: store.activity_types(hans).delete(k['activity_type'].id),
                                 NotFoundError),
    'get the schedule': (lambda store, k, hans: store.schedules(hans).get(k['schedule'].id), NotFoundError),
    'change the schedule': (lambda store, k, hans: store.schedules(hans).update(k['schedule'].model_copy(
        update={'weekly_minutes': 60})), NotFoundError),
    'delete the schedule': (lambda store, k, hans: store.schedules(hans).delete(k['schedule'].id), NotFoundError),
    'get the PTO year': (lambda store, k, hans: store.pto_years(hans).get(2026), NotFoundError),
    'delete the PTO year': (lambda store, k, hans: store.pto_years(hans).delete(2026), NotFoundError),
    'set the service of the ticket': (lambda store, k, hans: store.tickets(hans).set_service('TNG-4138', None),
                                      NotFoundError),
    'accept the invitation': (lambda store, k, hans: store.invitations().accept(hans, k['invitation'].id, store.teams()),
                              NotFoundError),
    'decline the invitation': (lambda store, k, hans: store.invitations().decline(hans, k['invitation'].id), NotFoundError),
}


def run(storage, action):
    with storage.transaction() as store:
        return action(store)


@pytest.mark.parametrize('attempt', ATTEMPTS)
def test_another_users_ids_are_unknown(storage, klaras, hans, attempt):
    action, error = ATTEMPTS[attempt]
    with pytest.raises(error):
        run(storage, lambda store: action(store, klaras, hans))


def test_another_users_records_cannot_be_used_or_seen(storage, klaras, hans, klara_id):
    activity = ActivityEntry(date=MONDAY, activity_type_id=klaras['activity_type'].id, duration=60)
    with pytest.raises(ConflictError):
        run(storage, lambda store: store.entries(hans).create(activity))
    run(storage, lambda store: store.tickets(hans).ensure('TNG-1'))
    with pytest.raises(ConflictError):
        run(storage, lambda store: store.tickets(hans).set_service('TNG-1', klaras['service'].id))
    with storage.transaction() as store:
        assert store.tickets(hans).get('TNG-4138') is None
        assert store.entries(hans).between(MONDAY, MONDAY) == [] and store.entries(hans).history(klaras['entry'].id) == []
        assert (store.days(hans).day_flags(), store.entries(hans).entry_flags(), store.services(hans).all()) == ([], [], [])
        assert store.entries(klara_id).get(klaras['entry'].id).description == 'secret'
