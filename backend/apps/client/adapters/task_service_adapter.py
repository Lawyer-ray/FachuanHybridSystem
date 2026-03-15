"""任务服务适配器实现。"""

from __future__ import annotations

import logging
from typing import Any

from apps.core.services.django_q_tasks import get_q_task_status, submit_q_task

logger = logging.getLogger(__name__)


class TaskServiceAdapter:
    """任务服务适配器。

    包装 django_q 任务服务，实现 TaskServicePort 接口。
    """

    def submit_task(
        self,
        func_path: str,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """提交异步任务。"""
        task_id: str = submit_q_task(func_path, *args, **kwargs)
        logger.debug("任务已提交", extra={"task_id": task_id, "func_path": func_path})
        return task_id

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """获取任务状态。"""
        result: dict[str, Any] = get_q_task_status(task_id)
        return result
