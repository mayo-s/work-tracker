"""The support page (SPEC 5.14): support users keep track of the contact messages, their status and notes, and find
earlier problems in the archive."""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.models.messages import ContactMessage
from src.modules.storage.messages import MessageRepository
from src.modules.storage.users import UserRepository
from src.tests.helpers import Clock, logged_in
from src.tests.users import HANS, PASSWORD, USER

MESSAGES = '/api/support/messages'
VISITOR = {'name': 'Rainer Zufall', 'email': 'rainer.zufall@example.com', 'subject': 'Access', 'text': 'May I join?'}


@pytest.fixture
def clock():
    return Clock(dt.datetime(2026, 11, 9, 9, 0))


@pytest.fixture
def app(database, clock):
    with database.transaction() as conn:
        UserRepository(conn).set_support(USER, True)  # Klara answers the messages
        UserRepository(conn).add(HANS, PASSWORD)
    return testing.TestClient(create_app(database, auth=True, clock=clock))


@pytest.fixture
def klara(app):
    return logged_in(app, 'klara')


def sent(app, clock, cookies=None, minutes=0, **changes):
    """The id of a message sent through the contact page."""
    clock.now += dt.timedelta(minutes=minutes)
    app.simulate_post('/api/contact', cookies=cookies, json=VISITOR | changes)
    return app.simulate_get(MESSAGES, cookies=logged_in(app, 'klara')).json['messages'][0]['id']


def test_only_support_reads_the_messages_and_gets_the_number_of_new_ones(app, klara):
    hans = logged_in(app, 'hans')
    assert app.simulate_get(MESSAGES).status == falcon.HTTP_401
    refused = app.simulate_get(MESSAGES, cookies=hans)
    assert (refused.status, refused.json['description']) == (falcon.HTTP_403, 'Only support reads the contact messages')
    app.simulate_post('/api/contact', json=VISITOR)
    assert app.simulate_get('/api/auth/status', cookies=klara).json['new_messages'] == 1
    assert app.simulate_get('/api/auth/status', cookies=hans).json['new_messages'] == 0


def test_messages_and_archive_with_the_sender_known_or_not(app, database, clock, klara):
    done = ContactMessage(sent_at=clock.now - dt.timedelta(days=100), name='Hans Dampf', email='hans.dampf@example.com',
                          subject='Export', text='The export stops.', status='done', known=True,
                          done_at=clock.now - dt.timedelta(days=90))
    with database.transaction() as conn:
        MessageRepository(conn).add(done)
    sent(app, clock)
    sent(app, clock, logged_in(app, 'hans'), minutes=1, subject='Login')
    found = app.simulate_get(MESSAGES, cookies=klara).json  # archives the one done for 90 days first
    assert [(item['subject'], item['name'], item['username'], item['known']) for item in found['messages']] == [
        ('Login', 'Hans Dampf', 'hans', True), ('Access', 'Rainer Zufall', None, False)]
    [archived] = found['archive']
    assert (archived['subject'], archived['email'], archived['username'], archived['known'], archived['archived']) == (
        'Export', '', None, True, True)


def test_status_and_notes_are_kept_with_who_and_when(app, clock, klara):
    message_id = sent(app, clock)
    item = f'{MESSAGES}/{message_id}'
    app.simulate_put(item, cookies=klara, json={'status': 'in_progress'})
    clock.now += dt.timedelta(hours=1)
    noted = app.simulate_post(f'{item}/notes', cookies=klara, json={'text': 'Asked Hans to invite him'})
    assert noted.status == falcon.HTTP_201
    done = app.simulate_put(item, cookies=klara, json={'status': 'done'}).json
    app.simulate_put(item, cookies=klara, json={'status': 'done'})  # no change
    assert (done['status'], done['done_at']) == ('done', '2026-11-09T10:00:00')
    assert [(change['at'], change['actor'], change['kind'], change['detail'])
            for change in app.simulate_get(item, cookies=klara).json['changes']] == [
        ('2026-11-09T09:00:00', 'Klara Himmel', 'status', 'in_progress'),
        ('2026-11-09T10:00:00', 'Klara Himmel', 'note', 'Asked Hans to invite him'),
        ('2026-11-09T10:00:00', 'Klara Himmel', 'status', 'done')]


def test_the_search_finds_all_words_in_subject_message_or_notes(app, clock, klara):
    noted = sent(app, clock, subject='Export')
    app.simulate_post(f'{MESSAGES}/{noted}/notes', cookies=klara, json={'text': 'Fixed in the CSV export'})
    sent(app, clock, minutes=1, subject='Login', text='The CSV link fails')

    def subjects(text):
        return [item['subject'] for item in app.simulate_get(MESSAGES, cookies=klara, params={'text': text}).json['messages']]

    assert (subjects('csv'), subjects('csv FIXED'), subjects('invoice')) == (['Login', 'Export'], ['Export'], [])


def test_an_archived_message_stays_as_it_is_but_can_be_deleted(app, database, clock, klara):
    archived = ContactMessage(sent_at=clock.now, name='Blue Elephant', subject='Export', text='The export stops.',
                              status='done', done_at=clock.now, anonymized=True)
    with database.transaction() as conn:
        message_id = MessageRepository(conn).add(archived).id
    item = f'{MESSAGES}/{message_id}'
    refused = app.simulate_put(item, cookies=klara, json={'status': 'new'})
    assert (refused.status, refused.json['description']) == (
        falcon.HTTP_409, 'An archived message stays as it is; it can only be deleted')
    assert app.simulate_post(f'{item}/notes', cookies=klara, json={'text': 'Fixed'}).status == falcon.HTTP_409
    assert app.simulate_delete(item, cookies=klara).status == falcon.HTTP_204
    assert app.simulate_get(item, cookies=klara).status == falcon.HTTP_404
