"""Django Q 任务入口。"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("apps.content_ops")


def execute_content_ops_task(task_id: str) -> dict[str, Any]:
    """内容运营管道执行入口（Django Q 调用）。"""
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

    from apps.content_ops.services.executor import ContentOpsExecutor

    logger.info("content_ops_task_start", extra={"task_id": task_id})
    executor = ContentOpsExecutor()
    result = executor.run(task_id=task_id)
    logger.info("content_ops_task_done", extra={"task_id": task_id, "status": result.get("status")})
    return result
