"""The people of the tests; the shared test database (conftest `database`) is set up for Klara."""

from src.models.users import User

USER = '5f0c2a9e-8b4d-4e1f-a6c3-2d7b9e1f4a08'  # Klara's id
PASSWORD = 'a long test password'
KLARA = User(username='klara', email='klara.himmel@example.com', first_name='Klara', last_name='Himmel')
HANS = User(username='hans', email='hans.dampf@example.com', first_name='Hans', last_name='Dampf')
RAINER = User(username='rainer', email='rainer.zufall@example.com', first_name='Rainer', last_name='Zufall')
PASCAL = User(username='pascal', email='turbo.pascal@example.com', first_name='Pascal', last_name='Turbo')
