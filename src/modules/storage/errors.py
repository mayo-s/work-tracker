"""Storage errors."""

from src.lib.texts import Text, text


class NotFoundError(LookupError):
    """Raised when a record to change or delete does not exist."""


class ConflictError(ValueError):
    """Raised when a change conflicts with existing data, e.g. a duplicate name or a record still in use."""


class SchemaVersionError(RuntimeError):
    """Raised when the database was created by a newer version of the app."""


class TooManyChangesError(ConflictError):
    """Raised when one change would write more items than DynamoDB can write together (100)."""


USED_TOKEN = text('This setup token was used already; create a new one (README, "Deploy to AWS")')
TAKEN = {'username': text('This username is already taken'), 'email': text('This e-mail address is already taken')}


def duplicate_name(label: str, name: str) -> Text:
    """The refusal of a second service or activity type (`label`) of the same name."""
    if label == 'service':
        return text('A service named "{name}" already exists', name=name)
    return text('An activity type named "{name}" already exists', name=name)


def used_by_entries(label: str) -> Text:
    """The refusal to delete a service or activity type (`label`) that entries use."""
    if label == 'service':
        return text('The service is used by entries and cannot be deleted')
    return text('The activity type is used by entries and cannot be deleted')
