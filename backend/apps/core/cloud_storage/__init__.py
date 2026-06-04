"""Cloud storage abstraction layer — unified interface for local / WebDAV / OneDrive."""

from .factory import create_provider_for_binding, create_provider_from_account
from .local import LocalProvider
from .models import CloudStorageAccount
from .null_provider import NullProvider
from .protocols import CloudFileInfo, CloudStorageProvider

__all__ = [
    "CloudFileInfo",
    "CloudStorageAccount",
    "CloudStorageProvider",
    "LocalProvider",
    "NullProvider",
    "create_provider_for_binding",
    "create_provider_from_account",
]
