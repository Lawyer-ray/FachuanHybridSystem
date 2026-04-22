"""Inode 解析服务：通过 inode+device 追踪移动/重命名后的文件夹路径."""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Any

logger = logging.getLogger("apps.core.filesystem")


class InodeResolver:
    """通过 inode + device 追踪文件夹路径.

    当文件夹被同卷 mv 移动后 inode 不变，可在 FOLDER_BROWSE_ROOTS
    范围内 BFS 搜索匹配 inode 的目录，自动修复路径.
    """

    def get_inode_info(self, folder_path: str) -> tuple[int, int] | None:
        """获取路径的 (inode, device) 元组.

        网络路径(SMB/UNC)或不存在路径返回 None.

        Args:
            folder_path: 文件夹绝对路径

        Returns:
            (inode, device) 元组或 None
        """
        try:
            p = Path(folder_path)
            if not p.exists():
                return None
            stat = p.stat()
            return (stat.st_ino, stat.st_dev)
        except (OSError, ValueError):
            return None

    def find_path_by_inode(
        self,
        inode: int,
        device: int,
        search_roots: list[Path],
        *,
        max_depth: int = 3,
        timeout_seconds: float = 5.0,
    ) -> str | None:
        """BFS 搜索匹配 inode+device 的目录路径.

        在 search_roots 范围内逐层搜索，找到第一个 inode+device 匹配
        的目录即返回其路径字符串.

        Args:
            inode: 目标 inode 编号
            device: 目标设备号
            search_roots: 搜索根目录列表（FOLDER_BROWSE_ROOTS）
            max_depth: 最大搜索深度，默认 3
            timeout_seconds: 搜索超时秒数，默认 5

        Returns:
            匹配的路径字符串或 None
        """
        start_time = time.monotonic()

        for root in search_roots:
            if not root.exists() or not root.is_dir():
                continue

            result = self._bfs_search(root, inode, device, max_depth, start_time, timeout_seconds)
            if result is not None:
                return result

            elapsed = time.monotonic() - start_time
            if elapsed >= timeout_seconds:
                logger.info(
                    "inode_search_timeout",
                    extra={"inode": inode, "device": device, "elapsed": f"{elapsed:.2f}s"},
                )
                return None

        return None

    def _bfs_search(
        self,
        root: Path,
        inode: int,
        device: int,
        max_depth: int,
        start_time: float,
        timeout_seconds: float,
    ) -> str | None:
        """在单个根目录下执行 BFS 搜索."""
        queue: deque[tuple[Path, int]] = deque([(root, 0)])

        while queue:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout_seconds:
                return None

            current_path, depth = queue.popleft()

            if depth > 0:
                try:
                    stat = current_path.stat()
                    if stat.st_ino == inode and stat.st_dev == device:
                        logger.info(
                            "inode_search_found",
                            extra={
                                "inode": inode,
                                "device": device,
                                "found_path": str(current_path),
                                "depth": depth,
                                "elapsed": f"{elapsed:.2f}s",
                            },
                        )
                        return str(current_path)
                except (OSError, PermissionError):
                    continue

            if depth < max_depth:
                try:
                    for child in current_path.iterdir():
                        if child.is_dir() and not child.is_symlink():
                            queue.append((child, depth + 1))
                except (OSError, PermissionError):
                    continue

        return None
