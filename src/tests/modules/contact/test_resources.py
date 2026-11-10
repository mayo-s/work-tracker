"""The contact page (SPEC 5.14): anyone writes to support, also without login; bots and floods are kept out."""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.models.messages import ContactMessage
from src.modules.storage.messages import MessageRepository
from src.tests.helpers import Clock, logged_in
from src.tests.users import KLARA, USER

MESSAGE = {'name': 'Rainer Zufall', 'email': 'rainer.zufall@example.com', 'subject': 'Access', 'text': 'May I join?'}


@pytest.fixture
def clock():
    return Clock(dt.datetime(2026, 11, 9, 9, 0))


@pytest.fixture
def app(database, clock):
    return testing.TestClient(create_app(database, auth=True, clock=clock))


def stored(database):
    with database.transaction() as conn:
        return [(row['name'], row['user_id']) for row in conn.execute('SELECT name, user_id FROM contact_messages')]


def send(app, cookies=None, **changes):
    return app.simulate_post('/api/contact', cookies=cookies, json=MESSAGE | changes)


def test_visitors_and_users_write_a_users_message_is_linked_to_them(app, database):
    page = app.simulate_get('/contact')
    assert (page.status, 'data-page="contact"' in page.text) == (falcon.HTTP_200, True)
    assert send(app).status == falcon.HTTP_201
    assert send(app, logged_in(app, 'klara'), name=KLARA.full_name, email=KLARA.email).status == falcon.HTTP_201
    assert stored(database) == [('Rainer Zufall', None), ('Klara Himmel', USER)]


def test_the_contact_page_is_there_before_the_setup(fresh_database):
    app = testing.TestClient(create_app(fresh_database, auth=True))
    assert (app.simulate_get('/contact').status, send(app).status) == (falcon.HTTP_200, falcon.HTTP_201)


def test_a_message_with_the_hidden_field_is_dropped(app, database):
    assert send(app, website='https://spam.example.com').status == falcon.HTTP_201  # the bot does not notice
    assert stored(database) == []


def test_visitors_pause_after_five_messages_within_ten_minutes(app, clock):
    for _ in range(5):
        send(app)
    refused = send(app)
    assert (refused.status, refused.json['description']) == (
        falcon.HTTP_429, 'Too many messages; try again in a few minutes')
    assert send(app, logged_in(app, 'klara')).status == falcon.HTTP_201  # logged in: no pause
    clock.now += dt.timedelta(minutes=10)
    assert send(app).status == falcon.HTTP_201


def test_a_message_needs_its_fields(app):
    result = send(app, email='rainer', text='')
    assert (result.status_code, sorted(error['loc'][0] for error in result.json)) == (422, ['email', 'text'])


def test_a_new_message_archives_the_due_ones(app, database, clock):
    done = ContactMessage(sent_at=clock.now - dt.timedelta(days=100), name='Klara Himmel', email=KLARA.email,
                          subject='Export', text='The export stops.', status='done',
                          done_at=clock.now - dt.timedelta(days=90))
    with database.transaction() as conn:
        MessageRepository(conn).add(done)
    send(app)
    assert [name for name, _ in stored(database)][0] != 'Klara Himmel'  # a color and an animal now
