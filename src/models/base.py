"""Base class for domain models."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid', validate_assignment=True)
