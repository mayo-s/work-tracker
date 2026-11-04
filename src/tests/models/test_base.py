from src.models.catalog import Service


def test_whole_numbers_are_read_as_ids_of_an_export_file():
    assert Service(id=3, short_name='MSB').id == '3'
