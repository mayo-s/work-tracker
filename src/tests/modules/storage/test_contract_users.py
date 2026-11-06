"""Users, sessions, login attempts and user settings: the same behaviour on SQLite and on DynamoDB (moto).

Each step runs in a transaction of its own, so the tests see what was stored, not only what one transaction holds.
"""

import datetime as dt
import uuid

import pytest

from src.models.settings import Settings
from src.models.users import TwoFactor
from src.modules.storage.errors import ConflictError, NotFoundError
from src.tests.helpers import run
from src.tests.users import KLARA, PASCAL, RAINER

LOGIN = dt.datetime(2026, 10, 29, 8, 0)
PASSWORD = 'correct horse battery 9!'


def add(storage, person):
    return run(storage, lambda store: store.users(clock=lambda: LOGIN).add(person, PASSWORD))


def start_session(storage, user_id, now=LOGIN):
    return run(storage, lambda store: store.sessions().start(user_id, now))


def session_user(storage, token, now=LOGIN):
    return run(storage, lambda store: store.sessions().user_id(token, now))


@pytest.fixture
def klara(storage):
    return add(storage, KLARA)


def test_the_first_user_is_admin(storage, klara):
    rainer = add(storage, RAINER)
    assert (klara.role, rainer.role) == ('admin', 'user')
    assert run(storage, lambda store: (store.users().count(), store.users().first_id())) == (2, klara.id)


def test_add_and_find_by_username_or_email_ignoring_case(storage, klara):
    rainer = add(storage, RAINER)
    assert run(storage, lambda store: store.users().by_login('RAINER')) == rainer
    assert run(storage, lambda store: store.users().by_login(' Rainer.Zufall@Example.com ')) == rainer
    assert run(storage, lambda store: store.users().by_login(PASCAL.username)) is None


def test_ids_are_random_uuids(storage, klara):
    rainer, pascal = add(storage, RAINER).id, add(storage, PASCAL).id
    assert (uuid.UUID(rainer).version, uuid.UUID(pascal).version) == (4, 4)
    assert rainer != pascal


@pytest.mark.parametrize('changes, field', [
    ({'username': 'RAINER'}, 'username'), ({'email': 'RAINER.ZUFALL@example.com'}, 'e-mail'),
])
def test_username_and_email_are_unique(storage, klara, changes, field):
    add(storage, RAINER)
    duplicate = RAINER.model_copy(update={'username': PASCAL.username, 'email': PASCAL.email} | changes)
    with pytest.raises(ConflictError, match=field):
        add(storage, duplicate)


def test_update_profile(storage, klara):
    changed = run(storage, lambda store: store.users().update(
        klara.model_copy(update={'last_name': 'Schuetz', 'email': 'k@example.com'})))
    assert run(storage, lambda store: store.users().get(klara.id)) == changed
    assert run(storage, lambda store: store.users().by_login('k@example.com')) == changed


def test_a_changed_username_is_free_for_others(storage, klara):
    run(storage, lambda store: store.users().update(klara.model_copy(update={'username': 'klara.himmel'})))
    assert run(storage, lambda store: store.users().by_login('klara')) is None
    assert add(storage, KLARA.model_copy(update={'email': 'other.klara@example.com'})).username == 'klara'


def test_changing_only_the_case_of_the_username(storage, klara):
    run(storage, lambda store: store.users().update(klara.model_copy(update={'username': 'Klara'})))
    assert run(storage, lambda store: store.users().by_login('KLARA')).username == 'Klara'


def test_an_update_cannot_take_the_email_of_another_user(storage, klara):
    add(storage, RAINER)
    with pytest.raises(ConflictError, match='e-mail'):
        run(storage, lambda store: store.users().update(klara.model_copy(update={'email': RAINER.email})))


def test_unknown_users(storage, klara):
    with pytest.raises(NotFoundError):
        run(storage, lambda store: store.users().get(str(uuid.uuid4())))


def test_password(storage, klara):
    assert run(storage, lambda store: store.users().check_password(klara.id, PASSWORD))
    token = start_session(storage, klara.id)
    run(storage, lambda store: store.users().set_password(klara.id, 'another long password 2#'))
    assert run(storage, lambda store: store.users().check_password(klara.id, 'another long password 2#'))
    assert not run(storage, lambda store: store.users().check_password(klara.id, PASSWORD))
    assert session_user(storage, token) == (None, False)  # all sessions ended


def test_session_lasts_24_hours_since_the_last_activity(storage, klara):
    token = start_session(storage, klara.id)
    assert session_user(storage, token, LOGIN + dt.timedelta(minutes=20)) == (klara.id, False)  # renewed every 30 min
    assert session_user(storage, token, LOGIN + dt.timedelta(hours=23)) == (klara.id, True)  # now valid to 23 h + 24 h
    assert session_user(storage, token, LOGIN + dt.timedelta(hours=46)) == (klara.id, True)
    assert session_user(storage, token, LOGIN + dt.timedelta(hours=70, minutes=1)) == (None, False)


def test_unknown_and_ended_sessions(storage, klara):
    token = start_session(storage, klara.id)
    assert session_user(storage, 'unknown') == (None, False)
    run(storage, lambda store: store.sessions().end(token))
    assert session_user(storage, token) == (None, False)


def test_failed_logins_pause_after_five_within_a_minute(storage):
    for second in range(5):
        assert not run(storage, lambda store: store.attempts().paused(LOGIN + dt.timedelta(seconds=second)))
        run(storage, lambda store: store.attempts().add(LOGIN + dt.timedelta(seconds=second)))
    assert run(storage, lambda store: store.attempts().paused(LOGIN + dt.timedelta(seconds=30)))
    assert not run(storage, lambda store: store.attempts().paused(LOGIN + dt.timedelta(seconds=61)))
    run(storage, lambda store: store.attempts().clear_failed(LOGIN + dt.timedelta(seconds=10)))
    assert not run(storage, lambda store: store.attempts().paused(LOGIN + dt.timedelta(seconds=30)))


def test_registrations_count_towards_the_pause_and_stay_after_a_login(storage):
    for second in range(4):
        run(storage, lambda store: store.attempts().add(LOGIN + dt.timedelta(seconds=second), 'registration'))
    run(storage, lambda store: store.attempts().add(LOGIN + dt.timedelta(seconds=4)))
    assert run(storage, lambda store: store.attempts().paused(LOGIN + dt.timedelta(seconds=5)))
    run(storage, lambda store: store.attempts().clear_failed(LOGIN + dt.timedelta(seconds=5)))
    assert not run(storage, lambda store: store.attempts().paused(LOGIN + dt.timedelta(seconds=5)))
    run(storage, lambda store: store.attempts().add(LOGIN + dt.timedelta(seconds=6), 'registration'))
    assert run(storage, lambda store: store.attempts().paused(LOGIN + dt.timedelta(seconds=7)))


def test_failed_logins_after_a_successful_one_count_again(storage):
    run(storage, lambda store: store.attempts().clear_failed(LOGIN))
    for second in range(1, 6):
        run(storage, lambda store: store.attempts().add(LOGIN + dt.timedelta(seconds=second)))
    assert run(storage, lambda store: store.attempts().paused(LOGIN + dt.timedelta(seconds=6)))


def test_a_user_records_registration_and_last_login(storage, klara):
    assert (klara.registered_at, klara.last_login_at, klara.active) == (LOGIN, None, True)
    start_session(storage, klara.id, LOGIN + dt.timedelta(hours=2))
    assert run(storage, lambda store: store.users().get(klara.id)).last_login_at == LOGIN + dt.timedelta(hours=2)


def test_all_users_in_the_order_they_registered(storage, klara):
    add(storage, RAINER)
    add(storage, PASCAL)
    assert [user.username for user in run(storage, lambda store: store.users().all())] == ['klara', 'rainer', 'pascal']


def test_change_role(storage, klara):
    rainer = add(storage, RAINER)
    assert run(storage, lambda store: store.users().set_role(rainer.id, 'admin')).role == 'admin'
    assert run(storage, lambda store: store.users().get(rainer.id)).role == 'admin'


def test_deactivating_ends_the_sessions_and_keeps_the_user(storage, klara):
    rainer = add(storage, RAINER)
    token = start_session(storage, rainer.id)
    assert run(storage, lambda store: store.users().set_active(rainer.id, False)).active is False
    assert session_user(storage, token) == (None, False)
    assert run(storage, lambda store: store.users().set_active(rainer.id, True)).active is True
    assert session_user(storage, start_session(storage, rainer.id)) == (rainer.id, False)


def test_settings_before_the_setup(storage, klara):
    rainer = add(storage, RAINER).id  # not the first user, who takes over what a new SQLite database seeds
    settings = run(storage, lambda store: store.load_settings(rainer))
    assert settings == Settings(balance_start=dt.date.today(), opening_balance=0, work_mode='tickets')
    assert run(storage, lambda store: (store.setup_done(rainer), store.load_theme(rainer))) == (False, 'system')


def test_save_settings_and_finish_the_setup(storage, klara):
    changed = Settings(balance_start=dt.date(2024, 6, 1), opening_balance=-90, work_mode='times')
    run(storage, lambda store: store.save_settings(klara.id, changed))
    run(storage, lambda store: store.finish_setup(klara.id))
    run(storage, lambda store: store.save_theme(klara.id, 'dark'))
    assert run(storage, lambda store: (store.load_settings(klara.id), store.setup_done(klara.id))) == (changed, True)
    assert run(storage, lambda store: store.load_theme(klara.id)) == 'dark'


def test_settings_are_per_user(storage, klara):
    rainer = add(storage, RAINER)
    run(storage, lambda store: store.save_theme(klara.id, 'dark'))
    run(storage, lambda store: store.finish_setup(klara.id))
    assert run(storage, lambda store: (store.load_theme(rainer.id), store.setup_done(rainer.id))) == ('system', False)


def test_there_is_only_one_root(storage, klara):
    root = add(storage, PASCAL.model_copy(update={'role': 'root'}))
    assert run(storage, lambda store: store.users().root_id()) == root.id
    with pytest.raises(ConflictError, match='There is a root already'):
        add(storage, RAINER.model_copy(update={'role': 'root'}))


def test_root_tracks_no_work(storage):
    root = add(storage, PASCAL.model_copy(update={'role': 'root'}))
    assert run(storage, lambda store: store.activity_types(root.id).all()) == []
    assert run(storage, lambda store: store.users().first_id()) is None  # with the login off, the app is nobody's


def test_the_first_user_is_the_first_who_is_not_root(storage):
    add(storage, PASCAL.model_copy(update={'role': 'root'}))
    rainer = add(storage, RAINER)
    assert run(storage, lambda store: store.users().first_id()) == rainer.id


def test_a_used_setup_token_is_refused_the_second_time(storage):
    run(storage, lambda store: store.use_setup_token('hash', LOGIN))
    run(storage, lambda store: store.use_setup_token('other hash', LOGIN))
    with pytest.raises(ConflictError, match='This setup token was used already'):
        run(storage, lambda store: store.use_setup_token('hash', LOGIN))


def test_two_factor_is_set_up_confirmed_and_switched_off(storage, klara):
    def users(action):
        return run(storage, lambda store: action(store.users()))

    confirmed = TwoFactor(secret='ABC', enabled=True, last_step=7)
    assert users(lambda repository: repository.two_factor(klara.id)) is None
    users(lambda repository: repository.save_two_factor(klara.id, TwoFactor(secret='ABC')))
    assert users(lambda repository: repository.get(klara.id)).two_factor is False  # not confirmed yet
    users(lambda repository: repository.save_two_factor(klara.id, confirmed))
    assert users(lambda repository: repository.two_factor(klara.id)) == confirmed
    assert users(lambda repository: repository.get(klara.id)).two_factor is True
    users(lambda repository: repository.save_two_factor(klara.id, None))
    assert users(lambda repository: repository.two_factor(klara.id)) is None


def test_a_new_authenticator_app_is_kept_until_confirmed(storage, klara):
    def users(action):
        return run(storage, lambda store: action(store.users()))

    with_new_app = TwoFactor(secret='ABC', enabled=True, last_step=7, new_secret='DEF')
    users(lambda repository: repository.save_two_factor(klara.id, with_new_app))
    assert users(lambda repository: repository.two_factor(klara.id)) == with_new_app
    users(lambda repository: repository.save_two_factor(klara.id, None))
    users(lambda repository: repository.save_two_factor(klara.id, TwoFactor(secret='GHI')))
    assert users(lambda repository: repository.two_factor(klara.id)).new_secret is None


def test_root_sessions_end_after_an_hour_without_activity(storage):
    root = add(storage, PASCAL.model_copy(update={'role': 'root'}))
    token = start_session(storage, root.id)
    assert session_user(storage, token, LOGIN + dt.timedelta(minutes=59)) == (root.id, True)  # renewed after 5 minutes
    assert session_user(storage, token, LOGIN + dt.timedelta(minutes=59 + 61))[0] is None


def browsers(storage, action):
    return run(storage, lambda store: action(store.browsers()))


def test_a_browser_is_remembered_for_30_days(storage, klara):
    token = browsers(storage, lambda repository: repository.remember(klara.id, LOGIN))
    assert browsers(storage, lambda repository: repository.known(klara.id, token, LOGIN + dt.timedelta(days=29)))
    assert not browsers(storage, lambda repository: repository.known(klara.id, token, LOGIN + dt.timedelta(days=31)))
    assert not browsers(storage, lambda repository: repository.known(klara.id, 'another token', LOGIN))


def test_a_browser_is_only_for_its_user(storage, klara):
    rainer = add(storage, RAINER)
    token = browsers(storage, lambda repository: repository.remember(klara.id, LOGIN))
    assert not browsers(storage, lambda repository: repository.known(rainer.id, token, LOGIN))


@pytest.mark.parametrize('change', [
    lambda users, user_id: users.set_password(user_id, 'another long password 2#'),
    lambda users, user_id: users.set_one_time_password(user_id, 'k7Qm-3xTp-9wLs-Rf2c'),
    lambda users, user_id: users.save_two_factor(user_id, None),
])
def test_a_new_password_or_two_factor_off_forgets_the_browsers(storage, klara, change):
    token = browsers(storage, lambda repository: repository.remember(klara.id, LOGIN))
    run(storage, lambda store: change(store.users(), klara.id))
    assert not browsers(storage, lambda repository: repository.known(klara.id, token, LOGIN))


def test_the_password_hash_for_the_backup(storage, klara):
    stored = run(storage, lambda store: store.users().password_hash(klara.id))
    assert stored.startswith('scrypt$') and PASSWORD not in stored
    with pytest.raises(NotFoundError):
        run(storage, lambda store: store.users().password_hash(str(uuid.uuid4())))
