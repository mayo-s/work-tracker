import json
from collections import defaultdict

from pydantic import BaseModel

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


def subclasses(model):
    return {model} | {found for subclass in model.__subclasses__() for found in subclasses(subclass)}


def test_models_of_the_same_name_have_the_same_schema():
    """The spec keeps one schema per name: a second model of that name would silently get the first one's schema."""
    names = openapi_document()['components']['schemas']
    schemas = defaultdict(set)
    for model in subclasses(BaseModel):
        if model.__name__ in names and model.__module__.startswith('src.') and '.tests.' not in model.__module__:
            schemas[model.__name__].add(json.dumps(model.model_json_schema(), sort_keys=True))
    assert [name for name, found in schemas.items() if len(found) > 1] == []
