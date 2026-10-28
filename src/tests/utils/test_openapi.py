from src.utils.openapi import SPEC_FILE, main, openapi_document, render


def test_spec_file_is_up_to_date():
    """If this fails, the API changed: run `npm run api-types` and commit openapi.json and api-types.ts."""
    assert SPEC_FILE.read_text(encoding='utf-8') == render(openapi_document())


def test_check_command(capsys):
    assert main(['--check']) == 0
    assert 'is up to date' in capsys.readouterr().out


def test_schema_names_are_plain():
    schemas = openapi_document()['components']['schemas']
    assert {'DayView', 'DayType', 'EntryView', 'ReviewView', 'MonthReport'} <= set(schemas)
    assert not any('.' in name for name in schemas)
