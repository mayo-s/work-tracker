"""Storage errors."""


class NotFoundError(LookupError):
    """Raised when a record to change or delete does not exist."""
