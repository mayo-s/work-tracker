"""Base class for domain models, and the ids of records."""

import uuid
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


class DomainModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid', validate_assignment=True)


def _as_text(value: object) -> object:
    """Whole numbers as text: the ids of an export file (1, 2, …)."""
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else value


RecordId = Annotated[str, BeforeValidator(_as_text), Field(description='A UUIDv7, e.g. 0190a3c4-5d2e-7f1a-9b3c-…')]


def new_id() -> str:
    """A new record id (SPEC 7.2a): a UUIDv7, which starts with the time of creation and is random after it."""
    return str(uuid.uuid7())
