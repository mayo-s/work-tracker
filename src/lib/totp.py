"""Time-based one-time passwords (RFC 6238), as authenticator apps make them: HMAC-SHA1 of the 30-second time step,
6 digits. One step before or after is accepted (clocks drift), and each step only once."""

import base64
import datetime as dt
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
ISSUER = 'Work Tracker'


def new_secret() -> str:
    """160 random bits in base32 without padding, the form authenticator apps take."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def time_step(moment: dt.datetime) -> int:
    return int(moment.timestamp()) // STEP_SECONDS


def code_at(secret: str, step: int) -> str:
    """The code of a time step (HOTP of RFC 4226 with the step as counter)."""
    key = base64.b32decode(secret + '=' * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack('>Q', step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10 ** DIGITS).zfill(DIGITS)


def matching_step(secret: str, code: str, moment: dt.datetime, after: int) -> int | None:
    """The time step the code belongs to (now, one before or one after), or None; steps up to `after` (the last one
    used) are refused, so a code works only once. Spaces in the code are ignored."""
    given = code.replace(' ', '')
    now = time_step(moment)
    for step in (now - 1, now, now + 1):
        if step > after and hmac.compare_digest(code_at(secret, step), given):
            return step
    return None


def provisioning_uri(secret: str, account: str) -> str:
    """The `otpauth://` address in the QR code: the app shows the issuer and the account."""
    label = quote(f'{ISSUER}:{account}')
    return f'otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&digits={DIGITS}&period={STEP_SECONDS}'
