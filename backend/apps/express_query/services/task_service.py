"""快递查询任务的查询与建单服务。

四层架构约定：API/Admin 层不直接碰 `Model.objects`，任务列表查询与建单入队下沉到此。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.core.security.admin_access import is_admin_user
from apps.core.tasking import submit_task
from apps.express_query.models import ExpressQueryTask, ExpressQueryTaskStatus

logger = logging.getLogger("apps.express_query")

# 列表返回上限：快递查询任务是历史记录型数据，前端不做分页，靠上限兜住响应体积。
TASK_LIST_LIMIT = 200

#: 手动输入运单号的入口（跳过 OCR，直接查浏览器）
MANUAL_INPUT_ENTRYPOINT = "apps.express_query.tasks.execute_manual_express_query_task"

#: 上传运单文件的入口（先 OCR 识别运单号再查浏览器）
UPLOAD_ENTRYPOINT = "apps.express_query.tasks.execute_express_query_task"


def list_visible_tasks(user: Any) -> Any:
    """返回当前用户可见的快递查询任务。

    管理员/超管看全量，其余人只看自己创建的任务。
    2026Q4 审计收紧：is_staff 仅是 Django admin 准入标志，不再视为系统管理员；
    管理员判定收敛到 ``core.security.admin_access.is_admin_user``。
    """
    queryset = ExpressQueryTask.objects.all()
    if not is_admin_user(user):
        queryset = queryset.filter(created_by=user)
    return queryset.order_by("-created_at")[:TASK_LIST_LIMIT]


def create_and_enqueue_manual(
    *,
    title: str,
    carrier_type: str,
    tracking_number: str,
    user: Any | None = None,
) -> ExpressQueryTask:
    """建「手动输入运单号」任务并入队（跳过 OCR，直接进入查询状态）。

    S39-03（2026-11-23 二轮审计）：原实现把「建任务 → save → submit_task →
    回写 queue_task_id → 日志」在 admin 的手动输入与上传两条路径里各写一份，
    改一侧漏另一侧即漂移（手动路径多写 ocr_text、上传路径没有）→ 现在两条路径
    统一收口到本模块 + ``_enqueue``，admin 只做参数提取与 message_user。
    """
    task = ExpressQueryTask(title=title or f"{carrier_type.upper()}-{tracking_number}")
    if user is not None and getattr(user, "is_authenticated", False):
        task.created_by = user

    # 直接设置承运商和运单号（跳过 OCR）
    task.carrier_type = carrier_type
    task.tracking_number = tracking_number
    task.ocr_text = "手动输入运单号"
    task.status = ExpressQueryTaskStatus.QUERYING
    task.save()

    _enqueue(
        task,
        MANUAL_INPUT_ENTRYPOINT,
        extra={"carrier_type": carrier_type, "tracking_number": tracking_number, "source": "manual_input"},
    )
    return task


def create_and_enqueue_upload(
    *,
    title: str,
    waybill_image: Any,
    user: Any | None = None,
) -> ExpressQueryTask:
    """建「上传运单文件」任务并入队（运单号由后台任务 OCR 识别）。"""
    task = ExpressQueryTask(title=title, waybill_image=waybill_image)
    if user is not None and getattr(user, "is_authenticated", False):
        task.created_by = user
    task.save()

    _enqueue(task, UPLOAD_ENTRYPOINT, extra={"source": "upload"})
    return task


def _enqueue(task: ExpressQueryTask, entrypoint: str, *, extra: dict[str, Any] | None = None) -> None:
    """把已落库的任务投递到后台队列，并回写 queue_task_id。"""
    queue_task_id = submit_task(entrypoint, task.id)
    task.queue_task_id = queue_task_id
    task.save(update_fields=["queue_task_id", "updated_at"])
    logger.info(
        "快递查询任务已创建并入队",
        extra={"task_id": task.id, "queue_task_id": queue_task_id, "entrypoint": entrypoint, **(extra or {})},
    )
