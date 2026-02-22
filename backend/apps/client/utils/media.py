"""公共媒体 URL 解析工具。"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def resolve_media_url(file_path: str) -> str | None:
    """将文件路径转换为媒体 URL。

    支持绝对路径（在 MEDIA_ROOT 下）和相对路径两种输入。

    Args:
        file_path: 文件路径字符串。

    Returns:
        媒体 URL 字符串，或 None（空路径/异常时）。
    """
    if not file_path:
        return None
    try:
        root = Path(settings.MEDIA_ROOT)
        p = Path(file_path)
        if p.is_absolute() and str(p).startswith(str(root)):
            rel = p.relative_to(root)
            return settings.MEDIA_URL + str(rel).replace("\\", "/")
        elif not p.is_absolute():
            return settings.MEDIA_URL + str(file_path).replace("\\", "/")
    except Exception:
        logger.exception("媒体URL解析失败", extra={"file_path": file_path})
        return None
    return None
