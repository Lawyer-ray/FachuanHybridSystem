"""Backward-compatible storage exports for client module."""

from apps.core.services.storage_service import (
    _get_media_root,
    delete_media_file,
    is_absolute_path,
    normalize_to_media_rel,
    sanitize_upload_filename,
    save_uploaded_file,
    to_media_abs,
)

__all__ = [
    "_get_media_root",
    "delete_media_file",
    "is_absolute_path",
    "normalize_to_media_rel",
    "sanitize_upload_filename",
    "save_uploaded_file",
    "to_media_abs",
]
