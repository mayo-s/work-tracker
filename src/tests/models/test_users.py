import pytest

from src.models.users import password_problem


def test_allowed_passwords():
    assert [password_problem(password) for password in ('a1!aaaaaaaaa', 'ÄÖÜäöüß 1234#')] == [None, None]


@pytest.mark.parametrize('password, problem', [
    ('a1!aaaaaaaa', 'at least 12 characters'),
    ('letters and 1234 digits', 'letters, digits and a special character'),
    ('1234567890!?', 'letters, digits and a special character'),
    ('no-digits-but-special', 'letters, digits and a special character'),
])
def test_refused_passwords(password, problem):
    assert problem in password_problem(password)
