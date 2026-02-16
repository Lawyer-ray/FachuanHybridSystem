"""
基于git的回滚管理器

在重构操作前创建checkpoint，失败时可回滚到之前的状态。
"""

from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .logging_config import get_logger

logger = get_logger("rollback")

_TAG_PREFIX = "refactor-checkpoint"


@dataclass
class Checkpoint:
    """回滚检查点"""

    checkpoint_id: str
    tag_name: str
    file_path: str
    message: str
    committed: bool = False


class RollbackManager:
    """
    基于git的回滚管理器

    使用git tag标记checkpoint，支持回滚到任意checkpoint。
    """

    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self._repo_root = repo_root or self._detect_repo_root()
        self._checkpoints: dict[str, Checkpoint] = {}

    # ── public API ──────────────────────────────────────────

    def create_checkpoint(self, file_path: str, message: str = "") -> str:
        """
        创建回滚检查点

        将当前工作区状态暂存并创建git tag。

        Args:
            file_path: 关联的文件路径
            message: checkpoint描述

        Returns:
            checkpoint_id
        """
        checkpoint_id = uuid.uuid4().hex[:12]
        tag_name = f"{_TAG_PREFIX}/{checkpoint_id}"
        desc = message or f"Checkpoint for {file_path}"

        # stage + commit 当前状态
        self._run_git("add", "-A")
        self._run_git("commit", "--allow-empty", "-m", f"[checkpoint] {desc}")
        self._run_git("tag", tag_name)

        cp = Checkpoint(
            checkpoint_id=checkpoint_id,
            tag_name=tag_name,
            file_path=file_path,
            message=desc,
        )
        self._checkpoints[checkpoint_id] = cp
        logger.info("Checkpoint created: %s (%s)", checkpoint_id, desc)
        return checkpoint_id

    def rollback(self, checkpoint_id: str) -> None:
        """
        回滚到指定检查点

        Args:
            checkpoint_id: 要回滚到的checkpoint

        Raises:
            ValueError: checkpoint不存在
        """
        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        self._run_git("reset", "--hard", cp.tag_name)
        logger.info("Rolled back to checkpoint: %s", checkpoint_id)

    def commit_changes(self, checkpoint_id: str, message: str) -> None:
        """
        确认更改，清理临时checkpoint tag

        Args:
            checkpoint_id: 要确认的checkpoint
            message: 提交消息
        """
        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        self._run_git("add", "-A")
        self._run_git("commit", "--allow-empty", "-m", message)
        self._cleanup_tag(cp.tag_name)
        cp.committed = True
        logger.info("Changes committed for checkpoint: %s", checkpoint_id)

    def cleanup_all(self) -> None:
        """清理所有未提交的checkpoint tag"""
        for cp in self._checkpoints.values():
            if not cp.committed:
                self._cleanup_tag(cp.tag_name)
        self._checkpoints.clear()
        logger.info("All checkpoints cleaned up")

    @property
    def checkpoints(self) -> dict[str, Checkpoint]:
        """返回当前所有checkpoint的只读副本"""
        return dict(self._checkpoints)

    # ── private helpers ─────────────────────────────────────

    def _detect_repo_root(self) -> Path:
        """检测git仓库根目录"""
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())

    def _run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        """执行git命令"""
        cmd = ["git", *args]
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            cwd=self._repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.error("Git command failed: %s\nstderr: %s", " ".join(cmd), result.stderr)
            raise RuntimeError(f"Git command failed: {' '.join(cmd)}\n{result.stderr}")
        return result

    def _cleanup_tag(self, tag_name: str) -> None:
        """删除git tag"""
        try:
            self._run_git("tag", "-d", tag_name)
        except RuntimeError:
            logger.warning("Failed to delete tag: %s (may not exist)", tag_name)
