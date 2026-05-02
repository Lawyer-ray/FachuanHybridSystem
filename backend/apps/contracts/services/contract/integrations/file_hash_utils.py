"""文件哈希与去重工具。"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: Path) -> str:
    """计算文件 SHA-256 哈希值。失败返回空字符串。"""
    try:
        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (OSError, ValueError):
        logger.exception("compute_file_hash_failed", extra={"path": file_path.as_posix()})
        return ""
