"""The archive of the messages (SPEC 5.14): 90 days after a message was last marked Done, its sender becomes a random
color and animal ("Blue Elephant"); subject, text and notes stay, so support finds earlier problems."""

import datetime as dt
import random
from collections.abc import Callable, Sequence

from src.models.messages import ContactMessage
from src.modules.storage.store import Store

KEPT = dt.timedelta(days=90)
COLORS = ('Amber', 'Black', 'Blue', 'Brown', 'Coral', 'Golden', 'Green', 'Grey', 'Indigo', 'Lilac', 'Mint', 'Orange',
          'Pink', 'Purple', 'Red', 'Silver', 'Teal', 'Turquoise', 'White', 'Yellow')
ANIMALS = ('Badger', 'Beaver', 'Camel', 'Crane', 'Dolphin', 'Eagle', 'Elephant', 'Falcon', 'Ferret', 'Flamingo', 'Fox',
           'Gecko', 'Giraffe', 'Hedgehog', 'Heron', 'Koala', 'Lemur', 'Lynx', 'Marten', 'Otter', 'Owl', 'Panda', 'Parrot',
           'Penguin', 'Raven', 'Seal', 'Sloth', 'Squirrel', 'Tiger', 'Turtle', 'Walrus', 'Whale', 'Wolf', 'Zebra')

Choose = Callable[[Sequence[str]], str]


def pseudonym(choose: Choose = random.choice) -> str:
    """A random color and animal, e.g. `Blue Elephant`: random for each message, so archived messages of the same sender
    cannot be told to be theirs."""
    return f'{choose(COLORS)} {choose(ANIMALS)}'


def due(message: ContactMessage, now: dt.datetime) -> bool:
    """Done for 90 days or more, and not anonymized yet."""
    return message.status == 'done' and not message.anonymized and message.done_at is not None \
        and now - message.done_at >= KEPT


def archive_due(store: Store, now: dt.datetime, choose: Choose = random.choice) -> int:
    """Anonymizes the messages that are due; the number of them. The app has no timer: this runs whenever support lists
    the messages and whenever a new one arrives."""
    messages = store.messages()
    archived = [message for message in messages.all() if due(message, now)]
    for message in archived:
        messages.anonymize(message.id, pseudonym(choose))
    return len(archived)
