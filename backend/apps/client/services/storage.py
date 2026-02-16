"""Business logic services."""

import logging
import re
import uuid
from typing import Any

from apps.core.config import get_config
from apps.core.exceptions import ValidationException
from apps.core.path import Path

logger = logging.getLogger(__name__)

_INVALID_FILENAME_CHARS = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._-]+")
_MULTIPLE_UNDERSCORES = re.compile(r"_+")
_WINDOWS_ABS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def sanitize_upload_filename(filename: str, max_length: int = 120) -> str:
    raw = (filename or "").replace("\\", "/").split("/")[-1].strip()
    raw = raw.strip(" .")
    if not raw:
        raw = "file"

    if "." in raw:
        stem, ext = raw.rsplit(".", 1)
        ext = "." + ext
    else:
        stem, ext = raw, ""

    stem = _INVALID_FILENAME_CHARS.sub("_", stem)
    stem = _MULTIPLE_UNDERSCORES.sub("_", stem)
    stem = stem.strip("._-") or "file"

    ext = _INVALID_FILENAME_CHARS.sub("", ext)
    ext = ext if ext.startswith(".") else ""

    safe = f"{stem}{ext}"
    if len(safe) > max_length:
        keep = max_length - len(ext)
        safe = f"{stem[:keep]}{ext}"
        safe = safe.strip(" .") or f"file{ext}"

    return safe


def is_absolute_path(path_str: str) -> bool:
    p = (path_str or "").strip()
    if not p:
        return False
    if p.startswith(("/", "\\")):
        return True
    return bool(_WINDOWS_ABS_PATH.match(p))


def to_media_abs(file_path: str) -> Path:
    if not file_path:
        raise ValidationException(
            message="文件路径不能为空", code="INVALID_FILE_PATH", errors={"file_path": "不能为空"}
        )
    media_root = get_config("django.media_root", None)
    if not media_root:
        raise ValidationException(
            message="MEDIA_ROOT 未配置", code="MEDIA_ROOT_NOT_CONFIGURED", errors={"MEDIA_ROOT": "未配置"}
        )
    root = Path(str(media_root)).resolve()
    p = Path(file_path)
    if not p.is_absolute():
        p = root / file_path
    try:
        p = p.resolve()
    except Exception:
        raise ValidationException(
            message="文件路径无效", code="INVALID_FILE_PATH", errors={"file_path": "无效"}
        ) from None
    try:
        p.relative_to(root)
    except ValueError:
        raise ValidationException(
            message="文件路径不在 MEDIA_ROOT 下",
            code="FILE_PATH_OUTSIDE_MEDIA_ROOT",
            errors={"file_path": "文件路径不在 MEDIA_ROOT 下"},
        ) from None
    return p


def normalize_to_media_rel(file_path: str) -> str:
    if not file_path:
        raise ValidationException(
            message="文件路径不能为空", code="INVALID_FILE_PATH", errors={"file_path": "不能为空"}
        )
    if not is_absolute_path(file_path):
        return file_path.replace("\\", "/").lstrip("/")

    media_root = get_config("django.media_root", None)
    if not media_root:
        raise ValidationException(
            message="MEDIA_ROOT 未配置", code="MEDIA_ROOT_NOT_CONFIGURED", errors={"MEDIA_ROOT": "未配置"}
        )
    root = Path(str(media_root)).resolve()
    p = Path(file_path)
    try:
        abs_path = p.resolve()
    except Exception:
        raise ValidationException(
            message="文件路径无效", code="INVALID_FILE_PATH", errors={"file_path": "无效"}
        ) from None
    try:
        rel = abs_path.relative_to(root)
    except ValueError:
        raise ValidationException(
            message="文件路径不在 MEDIA_ROOT 下",
            code="FILE_PATH_OUTSIDE_MEDIA_ROOT",
            errors={"file_path": "文件路径不在 MEDIA_ROOT 下"},
        ) from None
    return str(rel).replace("\\", "/")


def save_uploaded_file(
    uploaded_file: Any,
    rel_dir: str,
    preferred_filename: str | None = None,
    use_uuid_name: bool = True,
    max_size_bytes: int | None = None,
    allowed_extensions: list[str] | None = None,
    allowed_mime_types: list[str] | None = None,
) -> tuple[str, str]:
    if not hasattr(uploaded_file, "name"):
        raise ValidationException(message="上传文件缺少文件名", code="INVALID_UPLOAD", errors={"file": "缺少文件名"})

    original_name = str(getattr(uploaded_file, "name", "") or "")
    safe_original_name = sanitize_upload_filename(original_name)
    from apps.core.validators import Validators

    _max_size_bytes = int(max_size_bytes) if max_size_bytes is not None else 20 * 1024 * 1024
    Validators.validate_uploaded_file(  # type: ignore[attr-defined]
        uploaded_file,
        field_name="file",
        max_size_bytes=_max_size_bytes,
        allowed_extensions=allowed_extensions,
        allowed_mime_types=allowed_mime_types,
    )
    media_root = get_config("django.media_root", None)
    if not media_root:
        raise ValidationException(
            message="MEDIA_ROOT 未配置", code="MEDIA_ROOT_NOT_CONFIGURED", errors={"MEDIA_ROOT": "未配置"}
        )
    base_dir = Path(str(media_root)) / rel_dir

    if hasattr(base_dir, "makedirs_p"):
        base_dir.makedirs_p()
    else:
        import os

        os.makedirs(str(base_dir), exist_ok=True)

    preferred = preferred_filename or safe_original_name
    preferred = sanitize_upload_filename(preferred)
    preferred_ext = Path(preferred).suffix
    if not preferred_ext:
        preferred_ext = Path(safe_original_name).suffix
    ext = preferred_ext if preferred_ext and len(preferred_ext) <= 16 else ""

    if use_uuid_name:
        filename = f"{uuid.uuid4().hex}{ext}"
    else:
        filename = preferred

    target_abs = base_dir / filename
    while Path(str(target_abs)).exists():
        filename = f"{uuid.uuid4().hex}{ext}" if use_uuid_name else f"{uuid.uuid4().hex}_{preferred}"
        target_abs = base_dir / filename

    with open(str(target_abs), "wb+") as f:
        if hasattr(uploaded_file, "chunks"):
            for chunk in uploaded_file.chunks():
                f.write(chunk)
        else:
            f.write(uploaded_file.read())

    rel_path = Path(rel_dir) / filename
    return str(rel_path).replace("\\", "/"), safe_original_name


def delete_media_file(file_path: str) -> None:
    if not file_path:
        return

    media_root = get_config("django.media_root", None)
    if not media_root:
        return
    root = Path(str(media_root)).resolve()
    p = Path(file_path)
    if not p.is_absolute():
        p = root / file_path

    try:
        p = p.resolve()
    except Exception:
        logger.exception("操作失败")

        return

    try:
        p.relative_to(root)
    except ValueError:
        return

    try:
        p.unlink(missing_ok=True)
    except Exception:
        logger.exception("操作失败")

        return
