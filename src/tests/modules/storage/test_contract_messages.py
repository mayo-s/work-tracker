"""Contract tests of the messages of the contact page and their changes (SPEC 5.14), on both backends."""

import datetime as dt

import pytest

from src.models.messages import ContactMessage, MessageChange
from src.modules.storage.errors import NotFoundError
from src.tests.helpers import run
from src.tests.users import HANS, PASSWORD

SENT = dt.datetime(2026, 11, 9, 9, 0)


@pytest.fixture
def hans_id(storage, klara_id):
    return run(storage, lambda store: store.users().add(HANS, PASSWORD).id)


def send(storage, subject, minutes=0, user_id=None):
    message = ContactMessage(sent_at=SENT + dt.timedelta(minutes=minutes), name='Klara Himmel',
                             email='klara.himmel@example.com', subject=subject, text='The export stops.', user_id=user_id)
    return run(storage, lambda store: store.messages().add(message))


def change(storage, message_id, actor_id, kind, detail, minutes=0):
    return run(storage, lambda store: store.messages().add_change(MessageChange(
        message_id=message_id, at=SENT + dt.timedelta(hours=1, minutes=minutes), actor_id=actor_id, kind=kind,
        detail=detail)))


def test_messages_come_newest_first_with_their_changes_oldest_first(storage, klara_id, hans_id):
    first, second = send(storage, 'Export', user_id=klara_id), send(storage, 'Login', minutes=5)
    change(storage, first.id, hans_id, 'status', 'in_progress')
    change(storage, first.id, hans_id, 'note', 'Asked for the file', minutes=1)
    assert [message.subject for message in run(storage, lambda store: store.messages().all())] == ['Login', 'Export']
    assert run(storage, lambda store: store.messages().get(first.id)) == first
    changes = run(storage, lambda store: store.messages().changes(first.id))
    assert [(item.kind, item.detail, item.actor_name) for item in changes] == [
        ('status', 'in_progress', 'Hans Dampf'), ('note', 'Asked for the file', 'Hans Dampf')]
    assert run(storage, lambda store: store.messages().all_changes()) == changes
    assert second.user_id is None  # a visitor


def test_save_and_delete_with_the_changes(storage, klara_id, hans_id):
    message = send(storage, 'Export')
    change(storage, message.id, hans_id, 'note', 'Known problem')
    done = message.model_copy(update={'status': 'done', 'done_at': SENT})
    assert run(storage, lambda store: store.messages().save(done)) == done
    run(storage, lambda store: store.messages().delete(message.id))
    assert run(storage, lambda store: (store.messages().all(), store.messages().all_changes())) == ([], [])
    with pytest.raises(NotFoundError):
        run(storage, lambda store: store.messages().get(message.id))


def test_anonymizing_keeps_subject_text_and_notes(storage, klara_id, hans_id):
    message = send(storage, 'Export', user_id=klara_id)
    change(storage, message.id, hans_id, 'note', 'Klara sent the file')
    anonymized = run(storage, lambda store: store.messages().anonymize(message.id, 'Blue Elephant'))
    assert anonymized == message.model_copy(update={'name': 'Blue Elephant', 'email': '', 'user_id': None,
                                                    'anonymized': True})
    notes = run(storage, lambda store: store.messages().changes(message.id))
    assert [(item.actor_id, item.actor_name, item.detail) for item in notes] == [(None, 'Support', 'Klara sent the file')]


def test_restore_keeps_the_ids(storage, klara_id, hans_id):
    message = ContactMessage(id='0190a3c4-5d2e-7f1a-9b3c-000000000001', sent_at=SENT, name='Blue Elephant',
                             subject='Export', text='The export stops.', status='done', done_at=SENT, anonymized=True)
    note = MessageChange(id='0190a3c4-5d2e-7f1a-9b3c-000000000002', message_id=message.id, at=SENT, actor_id=None,
                         kind='note', detail='Fixed')
    run(storage, lambda store: (store.messages().restore(message), store.messages().restore_change(note)))
    assert run(storage, lambda store: store.messages().all()) == [message]
    changes = run(storage, lambda store: store.messages().changes(message.id))
    assert changes == [note.model_copy(update={'actor_name': 'Support'})]
