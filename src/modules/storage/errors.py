"""Storage errors."""


class NotFoundError(LookupError):
    """Raised when a record to change or delete does not exist."""


class ConflictError(ValueError):
    """Raised when a change conflicts with existing data, e.g. a duplicate name or a record still in use."""


class SchemaVersionError(RuntimeError):
    """Raised when the database was created by a newer version of the app."""


class TooManyChangesError(ConflictError):
    """Raised when one change would write more items than DynamoDB can write together (100)."""
