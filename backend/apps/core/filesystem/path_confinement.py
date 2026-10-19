"""文件系统路径校验工具（路径收敛 / 越界判定）。"""

from __future__ import annotations

from pathlib import Path


def is_within(root: Path, target: Path) -> bool:
    """判断 target 是否位于 root 之下（不含越界与跨盘；解耦 2026-10-19）。

    收敛 contracts/cases 两份 folder_scan_service 逐字相同的 ``_is_within_root``
    （os.path.commonpath 实现）。语义保持一致：Windows 下大小写不敏感的比较
    交给 commonpath，异常（跨盘等 ValueError）视为不在界内。
    """
    import os

    try:
        return os.path.commonpath([root.as_posix(), target.as_posix()]).replace("\\", "/") == root.as_posix()
    except ValueError:
        return False
