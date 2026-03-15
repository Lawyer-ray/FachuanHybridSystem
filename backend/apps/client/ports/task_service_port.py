"""任务服务端口。"""

from __future__ import annotations

from typing import Any, Protocol


class TaskServicePort(Protocol):
    """异步任务服务端口。

    封装对 django_q 任务队列的依赖。
    """

    def submit_task(
        self,
        func_path: str,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """提交异步任务。

        Args:
            func_path: 任务函数路径，如 "apps.client.tasks.execute_identity_doc_recognition"
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            任务ID
        """
        ...

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """获取任务状态。

        Args:
            task_id: 任务ID

        Returns:
            任务状态信息，包含 status、result、error 等字段
        """
        ...
