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
