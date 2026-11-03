"""Encryption with a passphrase (AES-256-GCM, key from scrypt) for the full backup."""

import base64
import json

import pytest

from src.lib.encryption import DecryptionError, decrypt, encrypt, read_header

PASSPHRASE = 'a long backup passphrase'
HEADER = {'format': 'work-tracker-backup', 'version': 1}


@pytest.fixture
def sealed():
    return encrypt(b'the whole database', PASSPHRASE, HEADER)


def with_header(sealed, **changes):
    head, _, rest = sealed.partition(b'\n')
    return json.dumps(json.loads(head) | changes).encode() + b'\n' + rest


def test_decrypted_with_the_passphrase(sealed):
    assert decrypt(sealed, PASSPHRASE) == b'the whole database'


def test_the_header_holds_the_fields_and_how_it_is_encrypted(sealed):
    header = read_header(sealed)
    assert (header['format'], header['version'], header['cipher'], header['kdf']['name']) == (
        'work-tracker-backup', 1, 'AES-256-GCM', 'scrypt')
    assert len(base64.b64decode(header['kdf']['salt'])) == 16 and len(base64.b64decode(header['nonce'])) == 12
    assert b'the whole database' not in sealed


def test_each_file_has_its_own_salt_and_nonce(sealed):
    again = read_header(encrypt(b'the whole database', PASSPHRASE, HEADER))
    assert (again['kdf']['salt'], again['nonce']) != (read_header(sealed)['kdf']['salt'], read_header(sealed)['nonce'])


def test_a_wrong_passphrase_is_refused(sealed):
    with pytest.raises(DecryptionError):
        decrypt(sealed, 'another passphrase')


def test_a_changed_header_is_noticed(sealed):
    changed = with_header(sealed, version=2)
    with pytest.raises(DecryptionError):
        decrypt(changed, PASSPHRASE)


def test_a_changed_ciphertext_is_noticed(sealed):
    changed = sealed[:-1] + bytes([sealed[-1] ^ 1])
    with pytest.raises(DecryptionError):
        decrypt(changed, PASSPHRASE)


@pytest.mark.parametrize('content', [b'no header line', b'[1, 2]\nrest', b'{not json\nrest'])
def test_a_file_without_header_is_refused(content):
    with pytest.raises(ValueError, match='The file has no header'):
        decrypt(content, PASSPHRASE)


@pytest.mark.parametrize('changes', [{'cipher': 'ChaCha20'}, {'kdf': {'name': 'scrypt', 'n': 2 ** 30, 'r': 8, 'p': 1,
                                                                      'salt': 'AAAA'}}])
def test_unknown_or_too_costly_encryption_is_refused(sealed, changes):
    changed = with_header(sealed, **changes)
    with pytest.raises(ValueError, match='encrypted in a way this Work Tracker does not read'):
        decrypt(changed, PASSPHRASE)


def test_an_incomplete_header_is_refused(sealed):
    changed = with_header(sealed, nonce=None)
    with pytest.raises(ValueError, match='The header is incomplete'):
        decrypt(changed, PASSPHRASE)


def test_the_real_parameters(monkeypatch):
    monkeypatch.setattr('src.lib.encryption._N', 2 ** 17)
    sealed = encrypt(b'data', PASSPHRASE, HEADER)
    assert read_header(sealed)['kdf'] | {'salt': ''} == {'name': 'scrypt', 'n': 2 ** 17, 'r': 8, 'p': 1, 'salt': ''}
    assert decrypt(sealed, PASSPHRASE) == b'data'
