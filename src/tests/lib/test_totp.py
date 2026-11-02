import datetime as dt

from src.lib.totp import code_at, matching_step, new_secret, provisioning_uri, time_step

# RFC 6238, appendix B: the SHA-1 secret "12345678901234567890" in base32, and its codes (the last 6 digits)
RFC_SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
MOMENT = dt.datetime.fromtimestamp(1111111109, dt.UTC)


def test_codes_of_the_rfc():
    assert code_at(RFC_SECRET, time_step(dt.datetime.fromtimestamp(59, dt.UTC))) == '287082'
    assert code_at(RFC_SECRET, time_step(MOMENT)) == '081804'
    assert code_at(RFC_SECRET, time_step(dt.datetime.fromtimestamp(1234567890, dt.UTC))) == '005924'


def test_one_step_before_or_after_is_accepted():
    step = time_step(MOMENT)
    for offset in (-1, 0, 1):
        assert matching_step(RFC_SECRET, code_at(RFC_SECRET, step + offset), MOMENT, 0) == step + offset
    assert matching_step(RFC_SECRET, code_at(RFC_SECRET, step + 2), MOMENT, 0) is None


def test_each_code_works_once():
    step = time_step(MOMENT)
    code = code_at(RFC_SECRET, step)
    assert matching_step(RFC_SECRET, code, MOMENT, after=step) is None
    assert matching_step(RFC_SECRET, code_at(RFC_SECRET, step + 1), MOMENT, after=step) == step + 1


def test_spaces_do_not_matter_and_wrong_codes_do_not_match():
    code = code_at(RFC_SECRET, time_step(MOMENT))
    assert matching_step(RFC_SECRET, f'{code[:3]} {code[3:]}', MOMENT, 0) is not None
    assert matching_step(RFC_SECRET, '000000' if code != '000000' else '111111', MOMENT, 0) is None


def test_new_secrets_are_random_base32():
    first, second = new_secret(), new_secret()
    assert first != second and len(first) == 32 and set(first) <= set('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567')


def test_the_address_for_the_app():
    assert provisioning_uri('ABC', 'klara') == (
        'otpauth://totp/Work%20Tracker%3Aklara?secret=ABC&issuer=Work%20Tracker&digits=6&period=30')
