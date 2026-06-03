"""Factory for creating the appropriate CloudStorageProvider."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .local import LocalProvider

if TYPE_CHECKING:
    from .protocols import CloudStorageProvider

logger = logging.getLogger(__name__)


def _get_nutstore_config_from_system_config() -> dict[str, str] | None:
    """Read Nutstore WebDAV credentials from SystemConfig (DB)."""
    try:
        from apps.core.services.system_config_service import SystemConfigService

        service = SystemConfigService()
        username = service.get_value("NUTSTORE_WEBDAV_USERNAME", "")
        password = service.get_value("NUTSTORE_WEBDAV_PASSWORD", "")
        if not username or not password:
            return None
        return {
            "username": username,
            "app_password": password,
        }
    except Exception:
        logger.exception("Failed to read Nutstore config from SystemConfig")
        return None


def create_provider_for_binding(binding) -> CloudStorageProvider:
    """Create a provider based on the binding's storage_type and storage_account."""
    storage_type = getattr(binding, "storage_type", "local")
    storage_account = getattr(binding, "storage_account", None)

    if storage_type == "local":
        return LocalProvider()

    if storage_type == "webdav":
        from .webdav_provider import JianguoyunProvider

        # Prefer CloudStorageAccount if linked
        if storage_account is not None:
            return JianguoyunProvider(
                username=storage_account.get_decrypted_webdav_username(),
                app_password=storage_account.get_decrypted_webdav_password(),
                root_path=getattr(storage_account, "webdav_root_path", "/"),
            )

        # Fallback to SystemConfig
        config = _get_nutstore_config_from_system_config()
        if config:
            return JianguoyunProvider(
                username=config["username"],
                app_password=config["app_password"],
            )

        logger.warning("No Nutstore WebDAV credentials configured")
        return LocalProvider()

    if storage_type == "onedrive":
        from .onedrive_provider import OneDriveProvider, OAuthTokenManager

        if storage_account is not None:
            token_manager = OAuthTokenManager(storage_account)
            return OneDriveProvider(
                access_token=token_manager.get_valid_token(),
                root_path=getattr(storage_account, "onedrive_root_path", "/"),
            )

        logger.warning("No OneDrive account linked")
        return LocalProvider()

    logger.warning("Unknown storage_type %r, falling back to local", storage_type)
    return LocalProvider()


def create_provider_from_account(account) -> CloudStorageProvider:
    """Create a provider directly from a CloudStorageAccount instance."""
    storage_type = account.storage_type

    if storage_type == "local":
        return LocalProvider(root=getattr(account, "local_root_path", "/"))

    if storage_type == "webdav":
        from .webdav_provider import JianguoyunProvider

        return JianguoyunProvider(
            username=account.get_decrypted_webdav_username(),
            app_password=account.get_decrypted_webdav_password(),
            root_path=getattr(account, "webdav_root_path", "/"),
        )

    if storage_type == "onedrive":
        from .onedrive_provider import OneDriveProvider, OAuthTokenManager

        token_manager = OAuthTokenManager(account)
        return OneDriveProvider(
            access_token=token_manager.get_valid_token(),
            root_path=getattr(account, "onedrive_root_path", "/"),
        )

    logger.warning("Unknown storage_type %r, falling back to local", storage_type)
    return LocalProvider()
