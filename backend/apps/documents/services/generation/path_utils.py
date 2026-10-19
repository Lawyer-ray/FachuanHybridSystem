"""Business logic services."""

from __future__ import annotations

import logging
from pathlib import Path

# 解耦（2026-10-19）：safe_name / safe_arcname 的实现已上提到 apps.core.filesystem.upload_paths
# （本模块被多个 app 引用、已成事实 core）。此处为兼容别名，保证既有 import 路径不变；
# 新代码请直接从 apps.core.filesystem.upload_paths 引入。
from apps.core.filesystem.upload_paths import safe_arcname, safe_name

logger = logging.getLogger(__name__)

__all__ = ["resolve_media_path", "safe_arcname", "safe_name"]


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
            # 安全审计 B-04：绝对路径仅当收敛在 MEDIA_ROOT 内才接受，防任意文件读
            try:
                resolved = p.resolve()
                root = Path(media_root).resolve()
                if resolved == root or root in resolved.parents:
                    return str(resolved)
            except OSError:
                return ""
            return ""
        return str(Path(media_root) / value)
    except Exception:
        logger.exception("操作失败")
        return ""
