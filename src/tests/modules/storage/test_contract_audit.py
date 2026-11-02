"""Contract tests of the audit log, on both backends."""

import datetime as dt

import pytest

from src.models.audit import AuditEntry
from src.models.teams import Team
from src.tests.users import HANS, PASSWORD

AT = dt.datetime(2026, 11, 2, 9, 0)


@pytest.fixture
def hans_id(storage, klara_id):
    with storage.transaction() as store:
        return store.users().add(HANS, PASSWORD).id


def add(storage, **entry):
    with storage.transaction() as store:
        store.audit_log().add(AuditEntry(**entry))


def read(storage, action):
    with storage.transaction() as store:
        return action(store.audit_log())


def test_entries_come_newest_first_with_names(storage, klara_id, hans_id):
    with storage.transaction() as store:
        team = store.teams().add(Team(name='Platform'))
    add(storage, actor_id=klara_id, action='role_changed', user_id=hans_id, detail='admin', at=AT)
    add(storage, actor_id=klara_id, action='team_created', team_id=team.id, at=AT + dt.timedelta(minutes=1))
    entries = read(storage, lambda log: log.latest())
    assert [(entry.action, entry.actor_name, entry.user_name, entry.team_name, entry.detail) for entry in entries] == [
        ('team_created', 'Klara Himmel', '', 'Platform', ''),
        ('role_changed', 'Klara Himmel', 'Hans Dampf', '', 'admin'),
    ]


def test_each_user_sees_the_entries_about_them(storage, klara_id, hans_id):
    add(storage, actor_id=klara_id, action='deactivated', user_id=hans_id, at=AT)
    add(storage, actor_id=klara_id, action='registration_switched', detail='on', at=AT)
    assert [entry.action for entry in read(storage, lambda log: log.of_user(hans_id))] == ['deactivated']
    assert read(storage, lambda log: log.of_user(klara_id)) == []  # Klara made the changes, they are not about her


def test_the_latest_only(storage, klara_id, hans_id):
    for minute in range(3):
        add(storage, actor_id=klara_id, action='one_time_password', user_id=hans_id, at=AT + dt.timedelta(minutes=minute))
    assert [entry.at.minute for entry in read(storage, lambda log: log.latest(limit=2))] == [2, 1]
    assert [entry.at.minute for entry in read(storage, lambda log: log.of_user(hans_id, limit=2))] == [2, 1]
