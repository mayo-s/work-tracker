"""Texts people read, written in English and answered in their language (SPEC 5.16).

`text('Unknown ticket {key}', key=key)` is the English sentence, as a str, that also keeps its template and values: where
the text leaves the app, the template is looked up in the language's catalog and the values filled in again.
"""

from collections.abc import Mapping
from typing import Any


def fill(template: str, params: Mapping[str, object]) -> str:
    """The template with its placeholders (`{name}`) filled in; braces of other kinds stay as they are."""
    for name, value in params.items():
        template = template.replace(f'{{{name}}}', str(value))
    return template


class Text(str):
    """An English text with the template and the values it was filled in from."""

    template: str
    params: dict[str, object]

    def __new__(cls, template: str, params: Mapping[str, object]) -> 'Text':
        filled = super().__new__(cls, fill(template, params))
        filled.template, filled.params = template, dict(params)
        return filled


def text(template: str, **params: object) -> Text:
    """A text people read; the template is a whole sentence of the catalogs, its values are not translated (except
    other texts)."""
    return Text(template, params)


def joined(texts: list[str], separator: str = '; ') -> Text:
    """Several texts as one, each translated on its own."""
    params = {f'part{number}': part for number, part in enumerate(texts)}
    return Text(separator.join(f'{{{name}}}' for name in params), params)


def raised_text(detail: Mapping[str, Any]) -> Text | None:
    """The text a validator raised as its ValueError, from an error of pydantic's `errors()`."""
    cause = detail.get('ctx', {}).get('error')
    if isinstance(cause, ValueError) and cause.args and isinstance(cause.args[0], Text):
        return cause.args[0]
    return None
