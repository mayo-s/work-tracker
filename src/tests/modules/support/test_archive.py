"""The archive (SPEC 5.14): 90 days after a message was last marked Done, its sender becomes a color and an animal."""

import datetime as dt

from src.models.messages import ContactMessage
from src.modules.support.archive import ANIMALS, COLORS, archive_due, due, pseudonym
from src.tests.helpers import run

NOW = dt.datetime(2026, 11, 9, 9, 0)
DONE = ContactMessage(sent_at=NOW - dt.timedelta(days=100), name='Klara Himmel', email='klara.himmel@example.com',
                      subject='Export', text='The export stops.', status='done', done_at=NOW - dt.timedelta(days=90))


def test_a_pseudonym_is_a_color_and_an_animal():
    assert pseudonym(lambda choices: choices[0]) == 'Amber Badger'
    color, animal = pseudonym().split(' ')
    assert (color in COLORS, animal in ANIMALS) == (True, True)


def test_due_after_90_days_done():
    assert [due(DONE, NOW), due(DONE, NOW - dt.timedelta(seconds=1)),
            due(DONE.model_copy(update={'status': 'in_progress'}), NOW),  # reopened
            due(DONE.model_copy(update={'anonymized': True}), NOW)] == [True, False, False, False]


def test_only_the_due_messages_are_anonymized(storage, klara_id):
    later = DONE.model_copy(update={'subject': 'Login', 'done_at': NOW - dt.timedelta(days=89)})
    run(storage, lambda store: (store.messages().add(DONE), store.messages().add(later)))
    assert run(storage, lambda store: archive_due(store, NOW, lambda choices: choices[-1])) == 1
    messages = run(storage, lambda store: store.messages().all())
    assert [(message.subject, message.name, message.email) for message in messages] == [  # sent at once: added last first
        ('Login', 'Klara Himmel', 'klara.himmel@example.com'), ('Export', 'Yellow Zebra', '')]
