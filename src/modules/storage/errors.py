"""Storage errors."""


class NotFoundError(LookupError):
    """Raised when a record to change or delete does not exist."""


class ConflictError(ValueError):
    """Raised when a change conflicts with existing data, e.g. a duplicate name or a record still in use."""
