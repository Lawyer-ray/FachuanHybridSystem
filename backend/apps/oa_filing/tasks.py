"""OA立案 / OA导入 任务入口。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.utils import timezone

from apps.core.tasking import TaskTimeoutError

logger = logging.getLogger("apps.oa_filing.tasks")


def run_client_import_task(session_id: int, headless: bool = True, limit: int | None = None) -> None:  # pragma: no cover
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


def run_case_import_preview_task(session_id: int, file_path: str) -> None:  # pragma: no cover
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


def run_case_import_task(  # pragma: no cover
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


def run_batch_create_cases_task(session_id: int, cases: list[dict[str, Any]]) -> None:  # pragma: no cover
    """Django-Q 任务入口：批量创建案件。

    从 ``batch_create_cases`` API 端点抽取的循环逻辑，
    避免大批次请求阻塞 HTTP 线程。
    """
    from apps.oa_filing.models import CaseImportSession
    from apps.oa_filing.services.case_import_service import CaseImportService
    from apps.oa_filing.services.oa_scripts.jtn.case_import import OACaseData

    try:
        session = CaseImportSession.objects.select_related("credential", "lawyer").get(pk=session_id)
    except CaseImportSession.DoesNotExist:
        logger.error("案件导入会话不存在: session_id=%s", session_id)
        return

    service = CaseImportService(session)

    success_count = 0
    skip_count = 0
    error_count = 0

    for case_data in cases:
        case_no = case_data.get("case_no", "")
        try:
            oa_data = OACaseData(case_no=case_no, keyid="")
            contract_id = service._create_or_update_case(oa_data)

            if contract_id:
                success_count += 1
            else:
                error_count += 1
        except Exception as exc:
            logger.warning("批量创建案件异常 %s: %s", case_no, exc)
            error_count += 1

    # 更新会话
    session.success_count = success_count
    session.skip_count = skip_count
    session.error_count = error_count
    session.save()

    logger.info(
        "批量创建案件完成: session_id=%d success=%d skip=%d error=%d",
        session_id,
        success_count,
        skip_count,
        error_count,
    )


def run_batch_create_clients_task(session_id: int, customers: list[dict[str, Any]]) -> None:  # pragma: no cover
    """Django-Q 任务入口：批量创建客户。

    从 ``batch_create_clients`` API 端点抽取的循环逻辑，
    避免大批次请求阻塞 HTTP 线程。
    """
    from apps.oa_filing.models import ClientImportSession
    from apps.oa_filing.services.import_session_service import (
        client_exists_by_id_number,
        client_exists_by_name,
        create_client_for_import,
    )

    try:
        session = ClientImportSession.objects.select_related("credential", "lawyer").get(pk=session_id)
    except ClientImportSession.DoesNotExist:
        logger.error("客户导入会话不存在: session_id=%s", session_id)
        return

    success_count = 0
    skip_count = 0
    error_count = 0

    for i, customer in enumerate(customers):
        try:
            name = customer.get("name", "").strip()
            client_type = customer.get("client_type", "natural")
            phone = customer.get("phone") or ""
            address = customer.get("address") or ""
            id_number_raw = customer.get("id_number")
            # 空字符串转为None，避免唯一约束冲突
            id_number = id_number_raw if id_number_raw and id_number_raw.strip() else None
            legal_representative = customer.get("legal_representative") or ""

            if not name:
                continue

            logger.info("[%d/%d] 处理: %s (type=%s)", i + 1, len(customers), name, client_type)

            if client_exists_by_name(name):
                skip_count += 1
                continue

            # 对于自然人，还要检查id_number是否已存在（避免身份证号冲突）
            if client_type == "natural" and id_number:
                if client_exists_by_id_number(id_number):
                    skip_count += 1
                    continue

            create_client_for_import(
                name=name,
                client_type=client_type,
                phone=phone,
                address=address,
                id_number=id_number,
                legal_representative=legal_representative,
            )
            success_count += 1

        except Exception as exc:
            error_count += 1
            logger.warning("  -> 创建客户失败: %s", exc)

    # 更新会话状态
    session.success_count = success_count
    session.skip_count = skip_count
    session.save()

    logger.info(
        "批量创建客户完成: session_id=%d success=%d skip=%d error=%d",
        session_id,
        success_count,
        skip_count,
        error_count,
    )
