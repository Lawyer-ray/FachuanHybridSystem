"""Factory for creating the appropriate CloudStorageProvider."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .local import LocalProvider
from .null_provider import NullProvider

if TYPE_CHECKING:
    from .protocols import CloudStorageProvider

logger = logging.getLogger(__name__)


def create_provider_for_binding(binding: Any) -> CloudStorageProvider:
    """Create a provider based on the binding's storage_type and storage_account.

    CloudStorageAccount is the single source of truth for credentials.
    """
    storage_type = getattr(binding, "storage_type", "local")
    storage_account = getattr(binding, "storage_account", None)

    if storage_type == "local":
        return LocalProvider()

    if storage_type == "webdav":
        from .webdav_provider import WebDAVProvider

        if storage_account is not None:
            return WebDAVProvider(
                username=storage_account.webdav_username,
                app_password=storage_account.get_decrypted_webdav_password(),
                root_path=getattr(storage_account, "webdav_root_path", "/"),
                webdav_url=getattr(storage_account, "webdav_url", ""),
            )

        logger.warning("No WebDAV account linked to binding")
        return NullProvider(reason="WebDAV 账号未配置或已禁用，请在 Admin 后台 -> 云存储账号 中配置")

    if storage_type == "onedrive":
        from .onedrive_provider import OAuthTokenManager, OneDriveProvider

        if storage_account is not None:
            token_manager = OAuthTokenManager(storage_account)
            return OneDriveProvider(
                access_token=token_manager.get_valid_token(),
                root_path=getattr(storage_account, "onedrive_root_path", "/"),
            )

        logger.warning("No OneDrive account linked to binding")
        return NullProvider(reason="OneDrive 账号未配置或已禁用，请在 Admin 后台 -> 云存储账号 中配置")

    logger.warning("Unknown storage_type %r", storage_type)
    return NullProvider(reason=f"不支持的存储类型: {storage_type}")


def create_provider_from_account(account: Any) -> CloudStorageProvider:
    """Create a provider directly from a CloudStorageAccount instance."""
    storage_type = account.storage_type

    if storage_type == "local":
        return LocalProvider(root=getattr(account, "local_root_path", "/"))

    if storage_type == "webdav":
        from .webdav_provider import WebDAVProvider

        return WebDAVProvider(
            username=account.webdav_username,
            app_password=account.get_decrypted_webdav_password(),
            root_path=getattr(account, "webdav_root_path", "/"),
            webdav_url=getattr(account, "webdav_url", ""),
        )

    if storage_type == "onedrive":
        from .onedrive_provider import OAuthTokenManager, OneDriveProvider

        token_manager = OAuthTokenManager(account)
        return OneDriveProvider(
            access_token=token_manager.get_valid_token(),
            root_path=getattr(account, "onedrive_root_path", "/"),
        )

    logger.warning("Unknown storage_type %r", storage_type)
    return NullProvider(reason=f"不支持的存储类型: {storage_type}")
