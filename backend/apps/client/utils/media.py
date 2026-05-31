"""公共媒体 URL 解析工具。"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# 缓存 MEDIA_ROOT 的 Path 对象和字符串形式，避免每次调用都重新构建
_cached_media_root: Path | None = None
_cached_media_root_str: str | None = None
_cached_media_url: str | None = None

def _get_media_root() -> tuple[Path, str, str]:
    """获取缓存的 MEDIA_ROOT 相关值。"""
    global _cached_media_root, _cached_media_root_str, _cached_media_url
    if _cached_media_root is None or _cached_media_url is None:
        _cached_media_root = Path(settings.MEDIA_ROOT)
        _cached_media_root_str = str(_cached_media_root)
        _cached_media_url = settings.MEDIA_URL
    return _cached_media_root, _cached_media_root_str or "", _cached_media_url or ""

@lru_cache(maxsize=1024)
def resolve_media_url(file_path: str) -> str | None:
    """将文件路径转换为媒体 URL。

    支持绝对路径（在 MEDIA_ROOT 下）和相对路径两种输入。
    结果会被缓存，相同输入不会重复计算。

    Args:
        file_path: 文件路径字符串。

    Returns:
        媒体 URL 字符串，或 None（空路径/异常时）。
    """
    if not file_path:
        return None
    try:
        root, root_str, media_url = _get_media_root()
        p = Path(file_path)
        if p.is_absolute() and str(p).startswith(root_str):
            rel = p.relative_to(root)
            return media_url + str(rel).replace("\\", "/")
        elif not p.is_absolute():
            return media_url + str(file_path).replace("\\", "/")
    except Exception:
        logger.exception("媒体URL解析失败", extra={"file_path": file_path})
        return None
    return None
