"""Conditions on the items of a query that DynamoDB checks itself (TASKS.md 14.4b): it returns only the matching items,
as a WHERE clause does on SQLite, so the app need not read a whole history to find the few items of the review.

Each condition is built once as both: the filter expression for DynamoDB and `matches` for items the transaction holds
already (its own writes, a range read before), so the two say the same.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

MAX_VALUES = 100  # DynamoDB takes up to 100 values in an `IN`; a larger filter is checked by the app instead

Item = dict[str, Any]


@dataclass(frozen=True)
class Filter:
    expression: str  # with `#name` for attributes and `:name` for values
    names: dict[str, str]
    values: dict[str, Any]
    matches: Callable[[Item], bool]

    @property
    def fits(self) -> bool:
        """Whether DynamoDB can take it."""
        return len(self.values) <= MAX_VALUES


def missing(name: str) -> Filter:
    """Without the attribute, or with none as its value (e.g. a ticket without service)."""
    expression = f'(attribute_not_exists(#{name}) OR attribute_type(#{name}, :null))'
    return Filter(expression, {f'#{name}': name}, {':null': 'NULL'}, lambda item: item.get(name) is None)


def present(name: str) -> Filter:
    expression = f'(attribute_exists(#{name}) AND NOT attribute_type(#{name}, :null))'
    return Filter(expression, {f'#{name}': name}, {':null': 'NULL'}, lambda item: item.get(name) is not None)


def equals(name: str, value: Any) -> Filter:
    return Filter(f'#{name} = :{name}', {f'#{name}': name}, {f':{name}': value}, lambda item: item.get(name) == value)


def one_of(name: str, values: Iterable[Any]) -> Filter:
    """With one of the values (at least one)."""
    wanted = sorted(set(values))
    placeholders = {f':{name}_{index}': value for index, value in enumerate(wanted)}
    return Filter(f'#{name} IN ({", ".join(placeholders)})', {f'#{name}': name}, placeholders,
                  lambda item: item.get(name) in wanted)


def both(*filters: Filter) -> Filter:
    return _joined(' AND ', filters, lambda item: all(part.matches(item) for part in filters))


def either(*filters: Filter) -> Filter:
    return _joined(' OR ', filters, lambda item: any(part.matches(item) for part in filters))


def _joined(operator: str, filters: tuple[Filter, ...], matches: Callable[[Item], bool]) -> Filter:
    names, values = {}, {}
    for part in filters:
        names |= part.names
        if any(values.get(key, value) != value for key, value in part.values.items()):
            raise ValueError(f'Two values for one name in {operator.join(each.expression for each in filters)}')
        values |= part.values
    return Filter(f'({operator.join(part.expression for part in filters)})', names, values, matches)
