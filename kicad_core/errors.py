"""Typed application errors with user-facing messages.

Every error that can reach the GUI carries a message that is safe to show
to a user.  Technical details are kept separately so the GUI can put them
behind a ``Details`` button and the logger can record them.  Errors never
carry tokens or client secrets - the code that raises them must not put
those values into a message.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for expected, recoverable application errors."""

    default_message = "Something went wrong."

    def __init__(self, message: str | None = None, *, details: str = "",
                 retry_after: int | None = None) -> None:
        self.message = message or self.default_message
        self.details = details
        self.retry_after = retry_after
        super().__init__(self.message)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class AuthRequired(AppError):
    """No usable token exists and the user must sign in again."""

    default_message = "DigiKey sign-in is required."


class AuthError(AppError):
    """The OAuth exchange or token file is invalid."""

    default_message = "DigiKey authentication failed."


class SearchError(AppError):
    """A product search failed for a reason explained by ``message``."""

    default_message = "The DigiKey search failed."


class RateLimitError(SearchError):
    """DigiKey returned HTTP 429."""

    default_message = "DigiKey rate limit reached. Wait a moment and retry."


class ServerError(SearchError):
    """DigiKey returned a 5xx error."""

    default_message = "DigiKey is temporarily unavailable. Retry in a moment."


class NetworkError(SearchError):
    """The DigiKey host could not be reached."""

    default_message = "Could not reach DigiKey. Check your network or proxy."


class ParseError(SearchError):
    """DigiKey returned malformed or unexpected data."""

    default_message = "DigiKey returned an unexpected response."


class DatabaseError(AppError):
    """A database operation failed."""

    default_message = "The database operation failed."


class DatabaseLockedError(DatabaseError):
    """SQLite reported ``database is locked``."""

    default_message = (
        "The database is in use (KiCad or another app). Close it and retry."
    )


class SchemaError(DatabaseError):
    """The chosen file is not a compatible components database."""

    default_message = "This file is not a compatible components database."


class BatchError(AppError):
    """A batch import failed before or during the run."""

    default_message = "The batch import failed."
