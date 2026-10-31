"""Password hashes with scrypt (standard library): `scrypt$n$r$p$salt$hash`, salt and hash in base64."""

import base64
import hashlib
import hmac
import secrets

_N, _R, _P = 2 ** 14, 8, 1  # 16 MiB of memory per hash
_PREFIX = 'scrypt'


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return '$'.join([_PREFIX, str(_N), str(_R), str(_P), _b64(salt), _b64(digest)])


_ALPHABET = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # without look-alikes (l, I, O, 0, 1)


def one_time_password() -> str:
    """A random password to pass on, e.g. `k7Qm-3xTp-9wLs-Rf2c`: four groups of four, with letters and digits; the
    dashes are the special characters a new password needs."""
    password = _groups()
    while not _letters_and_digits(password):
        password = _groups()
    return password


def _groups() -> str:
    return '-'.join(''.join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(4))


def _letters_and_digits(password: str) -> bool:
    return any(char.isalpha() for char in password) and any(char.isdigit() for char in password)


def verify_password(password: str, stored: str) -> bool:
    """True if the password matches the stored hash; compared in constant time."""
    try:
        prefix, n, r, p, salt, digest = stored.split('$')
    except ValueError:
        return False
    if prefix != _PREFIX:
        return False
    computed = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(computed, base64.b64decode(digest))


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode('ascii')
