"""Shared media storage helpers."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any, Protocol

from django.utils.translation import gettext_lazy as _

from apps.core.config import get_config
from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)

_INVALID_FILENAME_CHARS = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._-]+")
_MULTIPLE_UNDERSCORES = re.compile(r"_+")
_WINDOWS_ABS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


class FileValidator(Protocol):
    def validate_uploaded_file(
        self,
        uploaded_file: Any,
        allowed_extensions: list[str] | None = None,
        max_size_bytes: int | None = None,
        field_name: str = "file",
    ) -> Any: ...


class _DefaultFileValidator:
    """Fallback validator used outside app-specific adapters."""

    _EXECUTABLE_MAGIC: tuple[bytes, ...] = (
        b"MZ",
        b"\x7fELF",
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
    )

    def validate_uploaded_file(
        self,
        uploaded_file: Any,
        allowed_extensions: list[str] | None = None,
        max_size_bytes: int | None = None,
        field_name: str = "file",
    ) -> Any:
        if not uploaded_file:
            raise ValidationException("请选择要上传的文件", errors={field_name: "文件不能为空"})

        if allowed_extensions:
            normalized = {ext.lower() for ext in allowed_extensions}
            filename = str(getattr(uploaded_file, "name", "") or "")
            ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
            if ext not in normalized:
                raise ValidationException(
                    f"不支持的文件格式: {ext}",
                    errors={field_name: f"允许的格式: {', '.join(sorted(normalized))}"},
                )

        size = int(getattr(uploaded_file, "size", 0) or 0)
        if max_size_bytes is not None and size > max_size_bytes:
            raise ValidationException(
                "文件大小超限",
                errors={field_name: f"文件大小不能超过 {max_size_bytes} 字节"},
            )

        try:
            header: bytes = uploaded_file.read(8)
            uploaded_file.seek(0)
            if any(header.startswith(magic) for magic in self._EXECUTABLE_MAGIC):
                raise ValidationException(
                    "不允许上传可执行文件",
                    errors={field_name: "文件内容被识别为可执行文件"},
                )
        except (AttributeError, OSError):
            pass

        return uploaded_file


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


def _get_media_root() -> str | None:
    """Prefer Django settings MEDIA_ROOT, fallback to config."""
    from django.conf import settings as django_settings

    media_root = getattr(django_settings, "MEDIA_ROOT", None)
    if media_root:
        return str(media_root)
    result: str | None = get_config("django.media_root", None)
    return result


def to_media_abs(file_path: str) -> Path:
    if not file_path:
        raise ValidationException(
            message=_("文件路径不能为空"), code="INVALID_FILE_PATH", errors={"file_path": _("不能为空")}
        )
    media_root = _get_media_root()
    if not media_root:
        raise ValidationException(
            message=_("MEDIA_ROOT 未配置"), code="MEDIA_ROOT_NOT_CONFIGURED", errors={"MEDIA_ROOT": _("未配置")}
        )
    root = Path(media_root).resolve()
    p = Path(file_path)
    if not p.is_absolute():
        p = root / file_path
    try:
        p = p.resolve()
    except Exception:
        raise ValidationException(
            message=_("文件路径无效"), code="INVALID_FILE_PATH", errors={"file_path": _("无效")}
        ) from None
    try:
        p.relative_to(root)
    except ValueError:
        raise ValidationException(
            message=_("文件路径不在 MEDIA_ROOT 下"),
            code="FILE_PATH_OUTSIDE_MEDIA_ROOT",
            errors={"file_path": _("文件路径不在 MEDIA_ROOT 下")},
        ) from None
    return p


def normalize_to_media_rel(file_path: str) -> str:
    if not file_path:
        raise ValidationException(
            message=_("文件路径不能为空"), code="INVALID_FILE_PATH", errors={"file_path": _("不能为空")}
        )
    if not is_absolute_path(file_path):
        return file_path.replace("\\", "/").lstrip("/")

    media_root = _get_media_root()
    if not media_root:
        raise ValidationException(
            message=_("MEDIA_ROOT 未配置"), code="MEDIA_ROOT_NOT_CONFIGURED", errors={"MEDIA_ROOT": _("未配置")}
        )
    root = Path(media_root).resolve()
    p = Path(file_path)
    try:
        abs_path = p.resolve()
    except Exception:
        raise ValidationException(
            message=_("文件路径无效"), code="INVALID_FILE_PATH", errors={"file_path": _("无效")}
        ) from None
    try:
        rel = abs_path.relative_to(root)
    except ValueError:
        raise ValidationException(
            message=_("文件路径不在 MEDIA_ROOT 下"),
            code="FILE_PATH_OUTSIDE_MEDIA_ROOT",
            errors={"file_path": _("文件路径不在 MEDIA_ROOT 下")},
        ) from None
    return str(rel).replace("\\", "/")


def save_uploaded_file(
    uploaded_file: Any,
    rel_dir: str,
    preferred_filename: str | None = None,
    use_uuid_name: bool = True,
    max_size_bytes: int | None = None,
    allowed_extensions: list[str] | None = None,
    file_validator: FileValidator | None = None,
) -> tuple[str, str]:
    if not hasattr(uploaded_file, "name"):
        raise ValidationException(
            message=_("上传文件缺少文件名"), code="INVALID_UPLOAD", errors={"file": _("缺少文件名")}
        )

    original_name = str(getattr(uploaded_file, "name", "") or "")
    safe_original_name = sanitize_upload_filename(original_name)

    validator = file_validator if file_validator is not None else _DefaultFileValidator()
    _max_size_bytes = max_size_bytes if max_size_bytes is not None else 20 * 1024 * 1024
    validator.validate_uploaded_file(
        uploaded_file,
        field_name="file",
        max_size_bytes=_max_size_bytes,
        allowed_extensions=allowed_extensions,
    )
    media_root = _get_media_root()
    if not media_root:
        raise ValidationException(
            message=_("MEDIA_ROOT 未配置"), code="MEDIA_ROOT_NOT_CONFIGURED", errors={"MEDIA_ROOT": _("未配置")}
        )
    base_dir = Path(media_root) / rel_dir
    base_dir.mkdir(parents=True, exist_ok=True)

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
    while target_abs.exists():
        filename = f"{uuid.uuid4().hex}{ext}" if use_uuid_name else f"{uuid.uuid4().hex}_{preferred}"
        target_abs = base_dir / filename

    with open(target_abs, "wb+") as f:
        if hasattr(uploaded_file, "chunks"):
            for chunk in uploaded_file.chunks():
                f.write(chunk)
        else:
            f.write(uploaded_file.read())

    rel_path = Path(rel_dir) / filename
    return str(rel_path).replace("\\", "/"), safe_original_name


def delete_media_file(file_path: str) -> bool:
    if not file_path:
        return False

    media_root = _get_media_root()
    if not media_root:
        return False
    root = Path(media_root).resolve()
    p = Path(file_path)
    if not p.is_absolute():
        p = root / file_path

    try:
        p = p.resolve()
    except Exception:
        logger.exception("文件路径解析失败", extra={"file_path": file_path})
        return False

    try:
        p.relative_to(root)
    except ValueError:
        return False

    try:
        p.unlink(missing_ok=True)
    except Exception:
        logger.exception("删除媒体文件失败", extra={"file_path": file_path})
        return False

    return True


__all__ = [
    "_get_media_root",
    "delete_media_file",
    "is_absolute_path",
    "normalize_to_media_rel",
    "sanitize_upload_filename",
    "save_uploaded_file",
    "to_media_abs",
]
