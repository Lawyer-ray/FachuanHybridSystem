"""任务式（后台）入口的请求响应契约。"""

from __future__ import annotations

from ninja import Schema


class TaskIn(Schema):
    """提交后台任务。"""

    message: str
    title: str = ""
    case_id: int | None = None
    contract_id: int | None = None


class TaskOut(Schema):
    """后台任务的受理/状态回执。"""

    session_id: str
    task_id: str
    task_state: str
    title: str = ""
