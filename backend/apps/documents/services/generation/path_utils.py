"""Business logic services."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_media_path(media_root: str, file_path: str) -> str:
    try:
        value = (file_path or "").strip()
        if not value:
            return ""
        if value.startswith("http://") or value.startswith("https://"):
            return ""
        if value.startswith("/media/"):
            value = value[len("/media/") :]
        p = Path(value)
        if p.is_absolute():
            return str(p)
        return str(Path(media_root) / value)
    except Exception:
        logger.exception("操作失败")
        return ""


def safe_name(name: str) -> str:
    value = (name or "").strip()
    value = value.replace("/", "／").replace("\\", "＼")
    value = value.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return value or "未命名"


def safe_arcname(name: str) -> str:
    safe = (name or "").replace("\\", "/")
    safe = "/".join([safe_name(part) for part in safe.split("/") if part != ""])
    return safe
