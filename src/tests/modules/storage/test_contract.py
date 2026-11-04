"""The behaviour every storage backend shares (SPEC 7.2); runs on SQLite and on DynamoDB (simulated by moto)."""

import pytest


def test_migrating_again_keeps_the_version(storage):
    assert storage.migrate() == storage.migrate()


def test_registration_is_off_until_switched_on(storage):
    with storage.transaction() as store:
        assert store.registration_open() is False
        store.set_registration(True)
        assert store.registration_open() is True  # a transaction sees its own changes
    with storage.transaction() as store:
        assert store.registration_open() is True


def switch_registration_on_and_fail(storage):
    with storage.transaction() as store:
        store.set_registration(True)
        raise RuntimeError('something went wrong')


def test_a_failing_transaction_changes_nothing(storage):
    with pytest.raises(RuntimeError, match='something went wrong'):
        switch_registration_on_and_fail(storage)
    with storage.transaction() as store:
        assert store.registration_open() is False
