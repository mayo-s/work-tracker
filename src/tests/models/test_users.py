import pytest

from src.models.users import password_problem


@pytest.mark.parametrize('password', ['correct horse battery 9!', 'Passwört-2026', 'a1!aaaaaaaaa', 'ÄÖÜäöüß 1234#'])
def test_allowed_passwords(password):
    assert password_problem(password) is None


@pytest.mark.parametrize('password, problem', [
    ('a1!aaaaaaaa', 'at least 12 characters'),
    ('only letters and spaces', 'letters, digits and a special character'),
    ('letters and 1234 digits', 'letters, digits and a special character'),
    ('1234567890!?', 'letters, digits and a special character'),
    ('no-digits-but-special', 'letters, digits and a special character'),
])
def test_refused_passwords(password, problem):
    assert problem in password_problem(password)
