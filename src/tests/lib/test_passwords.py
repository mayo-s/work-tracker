import pytest

from src.lib.passwords import hash_password, verify_password


@pytest.fixture
def fast_password_hashes():
    """The real scrypt parameters here (overrides the cheap ones of conftest)."""


def test_hash_and_verify():
    stored = hash_password('correct horse battery 9!')
    assert stored.startswith('scrypt$16384$8$1$')
    assert verify_password('correct horse battery 9!', stored)
    assert not verify_password('correct horse batterY', stored)


def test_same_password_gets_a_new_salt():
    assert hash_password('correct horse battery 9!') != hash_password('correct horse battery 9!')


def test_unknown_formats_do_not_verify():
    assert not verify_password('x', 'plain')
    assert not verify_password('x', 'bcrypt$1$2$3$4$5')
