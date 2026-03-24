"""OA立案 / OA导入 任务入口。"""

from __future__ import annotations

import logging

from django.utils import timezone
from django_q.exceptions import TimeoutException

logger = logging.getLogger("apps.oa_filing.tasks")


def run_client_import_task(session_id: int, headless: bool = True, limit: int | None = None) -> None:
    """Django-Q 任务入口：执行 OA 客户导入。

    通过字符串路径 ``apps.oa_filing.tasks.run_client_import_task`` 调用。
    """
    from apps.oa_filing.models import ClientImportPhase, ClientImportSession, ClientImportStatus
    from apps.oa_filing.services.client_import_service import ClientImportService

    try:
        session = ClientImportSession.objects.select_related("credential", "lawyer").get(pk=session_id)
    except ClientImportSession.DoesNotExist:
        logger.error("客户导入会话不存在: session_id=%s", session_id)
        return

    if session.status in {ClientImportStatus.COMPLETED, ClientImportStatus.CANCELLED}:
        logger.info("会话已结束，跳过执行: session_id=%s status=%s", session_id, session.status)
        return

    # 若还未标记开始，先记录开始时间，避免前端长时间显示 pending。
    if session.started_at is None:
        session.started_at = timezone.now()
        session.status = ClientImportStatus.IN_PROGRESS
        session.phase = ClientImportPhase.DISCOVERING
        session.progress_message = "正在启动导入任务"
        session.error_message = ""
        session.save(update_fields=["started_at", "status", "phase", "progress_message", "error_message", "updated_at"])

    try:
        ClientImportService(session).run_import(headless=headless, limit=limit)
    except TimeoutException as exc:
        logger.exception("客户导入任务超时: session_id=%s error=%s", session_id, exc)
        session.status = ClientImportStatus.FAILED
        session.phase = ClientImportPhase.FAILED
        session.error_message = str(exc)
        session.progress_message = "导入超时"
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "phase", "error_message", "progress_message", "completed_at", "updated_at"])
        raise
    except Exception as exc:
        logger.exception("客户导入任务执行失败: session_id=%s error=%s", session_id, exc)
        session.status = ClientImportStatus.FAILED
        session.phase = ClientImportPhase.FAILED
        session.error_message = str(exc)
        session.progress_message = "导入失败"
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "phase", "error_message", "progress_message", "completed_at", "updated_at"])
