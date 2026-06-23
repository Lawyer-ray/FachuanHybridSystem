"""Shared helpers for cloud storage folder browsing in API endpoints."""

from __future__ import annotations

import logging
from asgiref.sync import sync_to_async
from pathlib import PurePosixPath
from typing import Any

from .exceptions import CloudStorageRateLimitError
from .models import CloudStorageAccount

logger = logging.getLogger("apps.core.cloud_storage")


def list_active_cloud_accounts() -> list[dict[str, Any]]:
    """Return active cloud storage accounts for folder binding UI."""
    qs = CloudStorageAccount.objects.filter(is_active=True).values(
        "id",
        "name",
        "storage_type",
        "local_root_path",
        "webdav_root_path",
        "onedrive_root_path",
        "s3_root_path",
        "gdrive_root_path",
        "dropbox_root_path",
    )
    return list(qs)  # type: ignore[arg-type]


def browse_cloud_folder(
    *,
    storage_type: str,
    storage_account_id: int,
    path: str | None = None,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Browse a cloud storage folder, returning a standardised result dict.

    Returns a dict with keys: browsable, message, path, parent_path, entries, storage_type.
    Caller converts to its own Schema type.
    """
    from .factory import create_provider_from_account

    account = CloudStorageAccount.objects.filter(
        id=storage_account_id, storage_type=storage_type, is_active=True
    ).first()
    if not account:
        return _error_result("云存储账号不存在", path, storage_type)

    provider = create_provider_from_account(account)
    browse_path = (path or "").strip().rstrip("/") or "/"

    try:
        children = provider.list_directory(browse_path)
    except CloudStorageRateLimitError as e:
        logger.warning("cloud_browse_rate_limited", extra={"path": browse_path, "account_id": storage_account_id})
        return _error_result(str(e), browse_path, storage_type)
    except Exception:
        logger.exception("cloud_browse_failed", extra={"path": browse_path, "account_id": storage_account_id})
        return _error_result("云存储目录访问失败，请稍后重试", browse_path, storage_type)

    entries: list[dict[str, str]] = []
    for child in children:
        if not child.is_dir:
            continue
        if not include_hidden and child.name.startswith("."):
            continue
        child_path = browse_path.rstrip("/") + "/" + child.name
        entries.append({"name": child.name, "path": child_path})
    entries.sort(key=lambda e: e["name"].lower())

    parent_path: str | None = None
    if browse_path != "/":
        parent_path = str(PurePosixPath(browse_path).parent)
        if parent_path == ".":
            parent_path = "/"
    else:
        parent_path = "/"

    return {
        "browsable": True,
        "message": None,
        "path": browse_path,
        "parent_path": parent_path,
        "entries": entries,
        "storage_type": storage_type,
    }


def _error_result(message: str, path: str | None, storage_type: str) -> dict[str, Any]:
    return {
        "browsable": False,
        "message": message,
        "path": path,
        "parent_path": None,
        "entries": [],
        "storage_type": storage_type,
    }


async def abrowse_cloud_folder(
    *,
    storage_type: str,
    storage_account_id: int,
    path: str | None = None,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Async version of :func:`browse_cloud_folder`.

    Uses ``provider.alist_directory`` for WebDAV/OneDrive providers and
    wraps the local provider with ``sync_to_async``.
    """
    from .factory import create_provider_from_account

    account = await sync_to_async(
        lambda: CloudStorageAccount.objects.filter(
            id=storage_account_id, storage_type=storage_type, is_active=True
        ).first()
    )()
    if not account:
        return _error_result("云存储账号不存在", path, storage_type)

    provider = create_provider_from_account(account)
    browse_path = (path or "").strip().rstrip("/") or "/"

    try:
        if hasattr(provider, "alist_directory"):
            children = await provider.alist_directory(browse_path)
        else:
            children = await sync_to_async(provider.list_directory)(browse_path)
    except CloudStorageRateLimitError as e:
        logger.warning("cloud_browse_rate_limited", extra={"path": browse_path, "account_id": storage_account_id})
        return _error_result(str(e), browse_path, storage_type)
    except Exception:
        logger.exception("cloud_browse_failed", extra={"path": browse_path, "account_id": storage_account_id})
        return _error_result("云存储目录访问失败，请稍后重试", browse_path, storage_type)

    entries: list[dict[str, str]] = []
    for child in children:
        if not child.is_dir:
            continue
        if not include_hidden and child.name.startswith("."):
            continue
        child_path = browse_path.rstrip("/") + "/" + child.name
        entries.append({"name": child.name, "path": child_path})
    entries.sort(key=lambda e: e["name"].lower())

    parent_path: str | None = None
    if browse_path != "/":
        parent_path = str(PurePosixPath(browse_path).parent)
        if parent_path == ".":
            parent_path = "/"
    else:
        parent_path = "/"

    return {
        "browsable": True,
        "message": None,
        "path": browse_path,
        "parent_path": parent_path,
        "entries": entries,
        "storage_type": storage_type,
    }
