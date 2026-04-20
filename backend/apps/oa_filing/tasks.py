"""OA立案 / OA导入 任务入口。"""

from __future__ import annotations

import logging
from pathlib import Path

from django.utils import timezone

from apps.core.tasking import TaskTimeoutError

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
    except TaskTimeoutError as exc:
        logger.exception("客户导入任务超时: session_id=%s error=%s", session_id, exc)
        session.status = ClientImportStatus.FAILED
        session.phase = ClientImportPhase.FAILED
        session.error_message = str(exc)
        session.progress_message = "导入超时"
        session.completed_at = timezone.now()
        session.save(
            update_fields=["status", "phase", "error_message", "progress_message", "completed_at", "updated_at"]
        )
        raise
    except Exception as exc:
        logger.exception("客户导入任务执行失败: session_id=%s error=%s", session_id, exc)
        session.status = ClientImportStatus.FAILED
        session.phase = ClientImportPhase.FAILED
        session.error_message = str(exc)
        session.progress_message = "导入失败"
        session.completed_at = timezone.now()
        session.save(
            update_fields=["status", "phase", "error_message", "progress_message", "completed_at", "updated_at"]
        )


def run_case_import_preview_task(session_id: int, file_path: str) -> None:
    """Django-Q 任务入口：预览 OA 案件导入。

    解析Excel文件，预览匹配结果。
    """
    from apps.oa_filing.models import CaseImportPhase, CaseImportSession, CaseImportStatus
    from apps.oa_filing.services.case_import_service import CaseImportService

    try:
        session = CaseImportSession.objects.select_related("credential", "lawyer").get(pk=session_id)
    except CaseImportSession.DoesNotExist:
        logger.error("案件导入会话不存在: session_id=%s", session_id)
        return

    if session.status in {CaseImportStatus.COMPLETED, CaseImportStatus.CANCELLED}:
        logger.info("会话已结束，跳过执行: session_id=%s status=%s", session_id, session.status)
        return

    try:
        # 更新状态为解析中
        session.started_at = timezone.now()
        session.status = CaseImportStatus.IN_PROGRESS
        session.phase = CaseImportPhase.PARSING
        session.progress_message = "正在解析Excel文件"
        session.save()

        # 解析Excel
        service = CaseImportService(session)
        case_nos = service.parse_excel(file_path)

        if not case_nos:
            session.status = CaseImportStatus.COMPLETED
            session.phase = CaseImportPhase.COMPLETED
            session.progress_message = "未从Excel中解析出案件编号"
            session.total_count = 0
            session.completed_at = timezone.now()
            session.save()
            return

        # 更新状态为预览
        session.phase = CaseImportPhase.PREVIEW
        session.total_count = len(case_nos)
        session.progress_message = f"解析完成，共 {len(case_nos)} 个案件，正在匹配"
        session.save()

        # 预览匹配
        preview_results = service.preview_cases(case_nos)

        # 统计
        matched_count = sum(1 for r in preview_results if r.status == "matched")
        unmatched_count = sum(1 for r in preview_results if r.status == "unmatched")
        error_count = sum(1 for r in preview_results if r.status == "error")

        # 保存预览结果
        session.matched_count = matched_count
        session.unmatched_count = unmatched_count
        session.error_count = error_count
        # 预览完成后保持pending状态，等待用户确认执行
        session.status = CaseImportStatus.PENDING
        session.phase = CaseImportPhase.PREVIEW
        session.progress_message = "预览完成，可开始导入"
        session.result_data = {
            "preview": [
                {
                    "case_no": r.case_no,
                    "status": r.status,
                    "existing_contract_id": r.existing_contract_id,
                    "customer_names": r.customer_names or [],
                    "error_message": r.error_message,
                }
                for r in preview_results
            ]
        }
        session.save()

        # 清理临时文件
        Path(file_path).unlink(missing_ok=True)

        logger.info(
            "案件预览完成: session_id=%d total=%d matched=%d unmatched=%d error=%d",
            session_id,
            len(case_nos),
            matched_count,
            unmatched_count,
            error_count,
        )

    except TaskTimeoutError as exc:
        logger.exception("案件预览任务超时: session_id=%s error=%s", session_id, exc)
        session.status = CaseImportStatus.FAILED
        session.phase = CaseImportPhase.FAILED
        session.error_message = str(exc)
        session.progress_message = "预览超时"
        session.completed_at = timezone.now()
        session.save()
        raise
    except Exception as exc:
        logger.exception("案件预览任务执行失败: session_id=%s error=%s", session_id, exc)
        session.status = CaseImportStatus.FAILED
        session.phase = CaseImportPhase.FAILED
        session.error_message = str(exc)
        session.progress_message = "预览失败"
        session.completed_at = timezone.now()
        session.save()


def run_case_import_task(
    session_id: int,
    case_nos: list[str],
    matched_case_nos: list[str] | None = None,
    headless: bool = True,
) -> None:
    """Django-Q 任务入口：执行 OA 案件导入。

    对预览阶段标记为 unmatched 的案件，从OA提取数据并创建/更新合同。
    """
    from apps.oa_filing.models import CaseImportPhase, CaseImportSession, CaseImportStatus
    from apps.oa_filing.services.case_import_service import CaseImportService

    try:
        session = CaseImportSession.objects.select_related("credential", "lawyer").get(pk=session_id)
    except CaseImportSession.DoesNotExist:
        logger.error("案件导入会话不存在: session_id=%s", session_id)
        return

    if session.status in {CaseImportStatus.COMPLETED, CaseImportStatus.CANCELLED}:
        logger.info("会话已结束，跳过执行: session_id=%s status=%s", session_id, session.status)
        return

    # 若还未标记开始，先记录开始时间
    if session.started_at is None:
        session.started_at = timezone.now()
        session.status = CaseImportStatus.IN_PROGRESS
        session.phase = CaseImportPhase.DISCOVERING
        session.progress_message = "正在启动导入任务"
        session.error_message = ""
        session.save(update_fields=["started_at", "status", "phase", "progress_message", "error_message", "updated_at"])

    try:
        service = CaseImportService(session)
        results = service.run_import(
            case_nos=case_nos,
            matched_case_nos=matched_case_nos,
            headless=headless,
        )

        # 结果已在 service.run_import 中保存到 session
        logger.info("案件导入任务完成: session_id=%d", session_id)

    except TaskTimeoutError as exc:
        logger.exception("案件导入任务超时: session_id=%s error=%s", session_id, exc)
        session.status = CaseImportStatus.FAILED
        session.phase = CaseImportPhase.FAILED
        session.error_message = str(exc)
        session.progress_message = "导入超时"
        session.completed_at = timezone.now()
        session.save(
            update_fields=["status", "phase", "error_message", "progress_message", "completed_at", "updated_at"]
        )
        raise
    except Exception as exc:
        logger.exception("案件导入任务执行失败: session_id=%s error=%s", session_id, exc)
        session.status = CaseImportStatus.FAILED
        session.phase = CaseImportPhase.FAILED
        session.error_message = str(exc)
        session.progress_message = "导入失败"
        session.completed_at = timezone.now()
        session.save(
            update_fields=["status", "phase", "error_message", "progress_message", "completed_at", "updated_at"]
        )
