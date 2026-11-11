"""Encryption with a passphrase (the full backup, SPEC 5.9): AES-256-GCM with a key from scrypt.

An encrypted file is a header line of JSON (the given fields, the scrypt parameters, salt and nonce: nothing secret)
and the ciphertext after it. The header is authenticated with the ciphertext, so changing either is noticed.
"""

import base64
import hashlib
import json
import secrets
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.lib.texts import text

_N, _R, _P = 2 ** 17, 8, 1  # 128 MiB of memory per key, as OWASP recommends for scrypt
_MAX_MEMORY = 2 ** 28  # 256 MiB: a file asking scrypt for more is refused rather than tying up the memory
_CIPHER = 'AES-256-GCM'


class DecryptionError(ValueError):
    """The passphrase is wrong or the file was changed or damaged (AES-GCM cannot tell which)."""


def encrypt(plain: bytes, passphrase: str, header: dict[str, Any]) -> bytes:
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    head = json.dumps(header | {'cipher': _CIPHER, 'kdf': {'name': 'scrypt', 'n': _N, 'r': _R, 'p': _P, 'salt': _b64(salt)},
                                'nonce': _b64(nonce)}).encode()
    return head + b'\n' + AESGCM(_key(passphrase, salt, _N, _R, _P)).encrypt(nonce, plain, head)


def read_header(sealed: bytes) -> dict[str, Any]:
    """The header line; ValueError if there is none."""
    head, separator, _ = sealed.partition(b'\n')
    try:
        header = json.loads(head) if separator else None
    except ValueError:
        header = None
    if not isinstance(header, dict):
        raise ValueError(text('The file has no header'))
    return header


def decrypt(sealed: bytes, passphrase: str) -> bytes:
    """The plain text; DecryptionError for a wrong passphrase or a changed file, ValueError for a header this code does
    not read."""
    salt, nonce, n, r, p = _parameters(read_header(sealed))
    head, _, ciphertext = sealed.partition(b'\n')
    try:
        return AESGCM(_key(passphrase, salt, n, r, p)).decrypt(nonce, ciphertext, head)
    except InvalidTag as error:
        raise DecryptionError(text('The passphrase is wrong, or the file is damaged')) from error


def _parameters(header: dict[str, Any]) -> tuple[bytes, bytes, int, int, int]:
    """Salt, nonce and the scrypt parameters n, r and p of the header."""
    kdf = header.get('kdf')
    try:
        salt, nonce, n, r, p = _unb64(kdf['salt']), _unb64(header['nonce']), int(kdf['n']), int(kdf['r']), int(kdf['p'])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(text('The header is incomplete')) from error
    if header.get('cipher') != _CIPHER or kdf.get('name') != 'scrypt' or not _affordable(n, r, p):
        raise ValueError(text('The file is encrypted in a way this Work Tracker does not read'))
    return salt, nonce, n, r, p


def _affordable(n: int, r: int, p: int) -> bool:
    """Whether scrypt with these parameters stays within the memory and time allowed."""
    return n > 1 and r > 0 and 0 < p <= 4 and 128 * r * n <= _MAX_MEMORY


def _key(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(passphrase.encode(), salt=salt, n=n, r=r, p=p, maxmem=2 * 128 * r * n, dklen=32)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _unb64(text: str) -> bytes:
    return base64.b64decode(text, validate=True)
