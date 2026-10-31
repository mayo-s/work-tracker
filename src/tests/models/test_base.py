import uuid

from src.models.base import new_id
from src.models.catalog import Service


def test_record_ids_are_uuid7_in_the_order_of_creation():
    ids = [new_id() for _ in range(1000)]
    assert {uuid.UUID(record_id).version for record_id in ids} == {7}
    assert ids == sorted(ids) and len(set(ids)) == 1000


def test_whole_numbers_are_read_as_ids_of_an_export_file():
    assert Service(id=3, short_name='MSB').id == '3'
