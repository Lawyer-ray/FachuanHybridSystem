"""活跃 asyncio 任务注册表

提供 TaskRegistry 单例，用于管理正在运行的批量分析 asyncio.Task 引用。
Service 层通过 registry 取消任务，而非直接 import task 模块的私有变量。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

class TaskRegistry:
    """管理活跃 asyncio 任务引用的注册表"""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def register(self, job_id: str, task: asyncio.Task[None]) -> None:
        """注册一个活跃任务"""
        self._tasks[job_id] = task

    def unregister(self, job_id: str) -> None:
        """移除任务引用"""
        self._tasks.pop(job_id, None)

    def cancel(self, job_id: str) -> bool:
        """取消指定任务，返回是否找到并取消成功"""
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            logger.info("已取消 asyncio task: job=%s", job_id)
            return True
        return False

    def get(self, job_id: str) -> asyncio.Task[None] | None:
        """获取活跃任务引用"""
        return self._tasks.get(job_id)

# 模块级单例
task_registry = TaskRegistry()
