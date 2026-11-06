"""Former ticket and activity entries (before TASKS.md 13.7) as entries of one kind (SPEC 4.6).

Shared by the SQLite migration, the DynamoDB migration and the import of an export file of version 1, so they convert
alike. A former entry comes as the fields of the former models: `kind` (`ticket` or `activity`), a ticket entry's
`ticket_key`, `description` and `coding`, an activity entry's `activity_type_id` and `note`.
"""

import re
from collections.abc import Callable
from typing import Any

from src.models.catalog import CODING

MEETING = 'Meeting'
_PR_REVIEW = re.compile(r'\bPR\b', re.IGNORECASE)
_REFINEMENT = re.compile(r'refinement', re.IGNORECASE)
_FORMER_FIELDS = ('kind', 'coding', 'note')


def ticket_activity_type(coding: bool, description: str) -> str | None:
    """The activity type of a former ticket entry: Coding for coding work and PR reviews (a look into code), Meeting
    for a refinement; None when unclear, so the review chooses one."""
    if coding or _PR_REVIEW.search(description):
        return CODING
    return MEETING if _REFINEMENT.search(description) else None


def convert(former: dict[str, Any], type_id: Callable[[str], str]) -> dict[str, Any]:
    """The fields of the entry of one kind: other fields (e.g. keys) stay. `type_id` gives the id of the user's activity
    type of a name, adding it if needed."""
    kept = {field: value for field, value in former.items() if field not in _FORMER_FIELDS}
    if former['kind'] == 'activity':
        return kept | {'ticket_key': None, 'description': former.get('note') or ''}
    return kept | {'activity_type_id': _ticket_type_id(former, type_id)}


def _ticket_type_id(former: dict[str, Any], type_id: Callable[[str], str]) -> str | None:
    name = ticket_activity_type(bool(former.get('coding')), former.get('description') or '')
    return type_id(name) if name else None
