"""Deleting the own account in the settings (SPEC 5.7, GDPR Art. 17): with the password and, with two-factor login on,
a code; then logged out."""

import datetime as dt

import falcon
import pytest
from falcon import testing

from src.app import create_app
from src.lib.totp import code_at, time_step
from src.models.users import TwoFactor
from src.modules.storage.users import UserRepository
from src.tests.helpers import logged_in, login
from src.tests.users import HANS, PASCAL, PASSWORD

NOW = dt.datetime(2026, 11, 10, 9, 0)
SECRET = 'JBSWY3DPEHPK3PXP'


@pytest.fixture
def app(database):
    with database.transaction() as conn:
        users = UserRepository(conn)
        hans = users.add(HANS, PASSWORD).id
        users.save_two_factor(hans, TwoFactor(secret=SECRET, enabled=True))
        users.add(PASCAL.model_copy(update={'role': 'root'}), PASSWORD)
    return testing.TestClient(create_app(database, auth=True, clock=lambda: NOW))


def delete(app, cookies, **body):
    result = app.simulate_delete('/api/auth/me', cookies=cookies, json=body)
    return result.status, (result.json or {}).get('description')


def test_with_the_password_and_the_code_the_account_goes_and_the_user_is_logged_out(app):
    hans = logged_in(app, 'hans', code=code_at(SECRET, time_step(NOW) - 1))
    assert delete(app, hans, password='wrong') == (falcon.HTTP_403, 'The current password is wrong')
    assert delete(app, hans, password=PASSWORD) == (
        falcon.HTTP_403, 'The code is wrong; enter the current one of your authenticator app, or a recovery code')
    result = app.simulate_delete('/api/auth/me', cookies=hans, json={'password': PASSWORD,
                                                                     'code': code_at(SECRET, time_step(NOW))})
    assert (result.status, result.cookies['wt_session'].value) == (falcon.HTTP_204, '')
    assert login(app, 'hans').status == falcon.HTTP_401


def test_root_is_never_deleted(app):
    pascal = logged_in(app, 'pascal')
    assert delete(app, pascal, password=PASSWORD) == (falcon.HTTP_409, 'Root runs the app and is never deleted')
