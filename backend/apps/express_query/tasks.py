from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from apps.core.filesystem.upload_paths import MediaEntity
from apps.core.services.storage_service import sanitize_upload_filename
from apps.express_query.models import ExpressQueryTask, ExpressQueryTaskStatus
from apps.express_query.services import ExpressBrowserQueryService, TrackingExtractionService
from apps.express_query.services.session_service import (
    SessionUnavailableError,
    mark_login_expired,
    mark_verified,
    resolve_session,
    session_lock,
)
from apps.express_query.services.tracking_extraction_service import truncate_pdf_to_first_page

logger = logging.getLogger("apps.express_query")

#: 无归属律师的历史任务回退到改造前的共享目录
_LEGACY_PROFILE_KEY: str = "express"


def execute_express_query_task(task_id: int) -> None:  # pragma: no cover
    """执行快递查询任务（从文件识别运单号）"""
    logger.info("开始执行快递查询任务", extra={"task_id": task_id})

    try:
        task = ExpressQueryTask.objects.get(id=task_id)
    except ExpressQueryTask.DoesNotExist:
        logger.error("快递查询任务不存在", extra={"task_id": task_id})
        return

    task.status = ExpressQueryTaskStatus.OCR_PARSING
    task.started_at = timezone.now()
    task.error_message = ""
    task.save(update_fields=["status", "started_at", "error_message", "updated_at"])

    try:
        extraction_service = TrackingExtractionService()
        extraction = extraction_service.extract(Path(task.waybill_image.path))

        task.ocr_text = extraction.ocr_text
        task.carrier_type = extraction.carrier_type
        task.tracking_number = extraction.tracking_number

        # PDF 只用第一页做 OCR，截断多页 PDF 节省空间
        if task.waybill_image and (task.waybill_image.name or "").endswith(".pdf"):
            truncate_pdf_to_first_page(Path(task.waybill_image.path))

        if not extraction.tracking_number:
            raise ValueError("OCR 未识别到有效运单号")

        if extraction.carrier_type not in {"sf", "ems"}:
            raise ValueError("OCR 已识别运单号，但未能识别承运商（仅支持 EMS/顺丰）")

        task.status = ExpressQueryTaskStatus.WAITING_LOGIN
        task.save(
            update_fields=[
                "ocr_text",
                "carrier_type",
                "tracking_number",
                "status",
                "updated_at",
            ]
        )

        # 继续执行浏览器查询（复用代码）
        _execute_browser_query(task)

    except Exception as exc:
        logger.exception("快递查询任务执行失败", extra={"task_id": task_id, "error": str(exc)})
        task.status = ExpressQueryTaskStatus.FAILED
        task.error_message = str(exc)
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error_message", "finished_at", "updated_at"])


def execute_manual_express_query_task(task_id: int) -> None:  # pragma: no cover
    """执行手动输入的快递查询任务（跳过OCR）"""
    logger.info("开始执行手动输入快递查询任务", extra={"task_id": task_id})

    try:
        task = ExpressQueryTask.objects.get(id=task_id)
    except ExpressQueryTask.DoesNotExist:
        logger.error("快递查询任务不存在", extra={"task_id": task_id})
        return

    task.started_at = timezone.now()
    task.error_message = ""
    task.save(update_fields=["started_at", "error_message", "updated_at"])

    try:
        # 验证承运商和运单号已设置
        if not task.tracking_number or not task.carrier_type:
            raise ValueError("缺少运单号或承运商信息")

        if task.carrier_type not in {"sf", "ems"}:
            raise ValueError(f"不支持的承运商: {task.carrier_type}（仅支持 SF/EMS）")

        # 直接执行浏览器查询
        _execute_browser_query(task)

    except Exception as exc:
        logger.exception("手动输入快递查询任务执行失败", extra={"task_id": task_id, "error": str(exc)})
        task.status = ExpressQueryTaskStatus.FAILED
        task.error_message = str(exc)
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error_message", "finished_at", "updated_at"])


def _execute_browser_query(task: ExpressQueryTask) -> None:
    """执行浏览器查询（公共逻辑）。

    流程：
    1. 解析该律师在对应承运商下的扫码会话
    2. 无可用会话 → 转入「等待登录」并释放 worker（不再死等扫码）
    3. 有会话 → 加锁串行执行；期间若发现登录失效，同样转「等待登录」
    """
    session = resolve_session(task)

    if session is not None and not session.is_ready:
        logger.info(
            "会话未登录，任务转入等待登录",
            extra={"task_id": task.id, "session_id": session.id, "status": session.status},
        )
        task.status = ExpressQueryTaskStatus.WAITING_LOGIN
        task.error_message = "该账号尚未扫码登录，请在「快递账号会话」中完成扫码后重试"
        task.save(update_fields=["status", "error_message", "updated_at"])
        return

    profile_key = session.profile_key if session is not None else _LEGACY_PROFILE_KEY

    task.status = ExpressQueryTaskStatus.QUERYING
    task.save(update_fields=["status", "updated_at"])

    # page.pdf 先写系统临时文件，再经 default_storage 保存到 media（文件名不可预测化）
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        tmp_pdf_path = Path(tmp_file.name)

    try:
        from apps.express_query.services.browser_query.ems_query_handler import ExpressLoginRequired as EmsLoginRequired
        from apps.express_query.services.browser_query.sf_query_handler import ExpressLoginRequired as SfLoginRequired

        browser_service = ExpressBrowserQueryService()
        coro = browser_service.query_and_save_pdf(
            carrier_type=task.carrier_type,
            tracking_number=task.tracking_number,
            output_pdf=tmp_pdf_path,
            profile_key=profile_key,
            # 无人值守：未登录立刻返回，而不是死等 300s 占满 worker
            allow_interactive_login=False,
        )

        # 浏览器的启动与关闭由 query_and_save_pdf 用 async with 自包含，
        # 保证在同一个 asyncio.run() 生命周期内完成。
        # 若把浏览器实例或 async context manager 跨循环持有，
        # asyncio.run() 收尾的 shutdown_asyncgens 会永久阻塞，任务卡在“查询中”。
        #
        # Django-Q2 worker 没有运行中的事件循环，直接用 asyncio.run()
        with session_lock(session):
            try:
                final_url = asyncio.run(coro)
            except (EmsLoginRequired, SfLoginRequired) as exc:
                _handle_login_required(task, session, str(exc))
                return
        pdf_content = tmp_pdf_path.read_bytes()
    finally:
        tmp_pdf_path.unlink(missing_ok=True)

    safe_name = sanitize_upload_filename(f"{task.tracking_number}.pdf")
    rel_path = f"{MediaEntity.EXPRESS_QUERY_RESULTS}/{task.id}/{uuid.uuid4().hex[:8]}_{safe_name}"
    saved_name = default_storage.save(rel_path, ContentFile(pdf_content))

    task.status = ExpressQueryTaskStatus.SUCCESS
    task.query_url = final_url
    task.result_pdf.name = saved_name
    task.result_payload = {
        "carrier_type": task.carrier_type,
        "tracking_number": task.tracking_number,
        "query_url": final_url,
        "pdf_path": saved_name,
    }
    task.finished_at = timezone.now()
    task.save(
        update_fields=[
            "status",
            "query_url",
            "result_pdf",
            "result_payload",
            "finished_at",
            "updated_at",
        ]
    )
    logger.info("快递查询任务执行成功", extra={"task_id": task.id})


def _handle_login_required(task: ExpressQueryTask, session: object, reason: str) -> None:
    """查询中发现未登录：把会话标记失效，任务转「等待登录」。"""
    if session is not None:
        mark_login_expired(session, reason)  # type: ignore[arg-type]

    task.status = ExpressQueryTaskStatus.WAITING_LOGIN
    task.error_message = f"{reason}——请在「快递账号会话」中扫码登录后重试"
    task.save(update_fields=["status", "error_message", "updated_at"])
    logger.info("任务转入等待登录", extra={"task_id": task.id, "reason": reason})


def open_login_browser_task(lawyer_id: int, carrier_type: str) -> None:  # pragma: no cover
    """打开有头浏览器，等待律师扫码登录，成功后激活会话。

    这是唯一需要人工参与的环节；扫码完成后会话状态置为 active，
    后续查询任务即可直接复用该登录态。
    """
    from apps.express_query.models import ExpressSession
    from apps.express_query.services.session_service import mark_login_success
    from apps.organization.models import Lawyer

    try:
        lawyer = Lawyer.objects.get(id=lawyer_id)
    except Lawyer.DoesNotExist:
        logger.error("扫码任务：律师不存在", extra={"lawyer_id": lawyer_id})
        return

    session, _ = ExpressSession.objects.get_or_create(
        lawyer=lawyer,
        carrier_type=carrier_type,
    )

    async def _run() -> None:
        from apps.core.services.browser import create_browser_async
        from apps.core.services.browser.profiles import get_express_profile
        from apps.express_query.services.browser_query.ems_auth_handler import (
            ems_click_login_button,
            ems_handle_agreement_and_wait,
        )

        profile = get_express_profile(session.profile_key)
        async with create_browser_async(profile) as (page, _context):
            await page.goto("https://www.11183.com.cn/?to=%2Fquery_express_delivery", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await ems_click_login_button(page)
            await asyncio.sleep(1.5)
            await ems_handle_agreement_and_wait(_context, page, timeout_seconds=300)

    try:
        asyncio.run(_run())
        mark_login_success(session)
        logger.info("扫码登录成功", extra={"session_id": session.id})
    except Exception as exc:
        mark_login_expired(session, str(exc))
        logger.exception("扫码登录失败", extra={"session_id": session.id})
