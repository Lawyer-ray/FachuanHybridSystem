"""Cloud storage specific exceptions."""

from __future__ import annotations


class CloudStorageError(Exception):
    """Base exception for cloud storage operations.

    Attributes:
        provider: Storage provider name (e.g. "坚果云 WebDAV", "OneDrive")
        retry_after: Suggested seconds to wait before retrying (None if unknown)
    """

    def __init__(self, message: str, *, provider: str = "", retry_after: int | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.retry_after = retry_after


class CloudStorageRateLimitError(CloudStorageError):
    """Raised when the cloud storage service returns a rate limit (HTTP 503/429)."""

    def __init__(self, message: str, *, provider: str = "", retry_after: int | None = None) -> None:
        super().__init__(message, provider=provider, retry_after=retry_after)
