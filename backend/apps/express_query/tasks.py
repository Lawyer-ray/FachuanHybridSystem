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

logger = logging.getLogger("apps.express_query")


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
            TrackingExtractionService.truncate_pdf_to_first_page(Path(task.waybill_image.path))

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
        logger.error("快递查询任务执行失败", extra={"task_id": task_id, "error": str(exc)}, exc_info=True)
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
        logger.error("手动输入快递查询任务执行失败", extra={"task_id": task_id, "error": str(exc)}, exc_info=True)
        task.status = ExpressQueryTaskStatus.FAILED
        task.error_message = str(exc)
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error_message", "finished_at", "updated_at"])


def _execute_browser_query(task: ExpressQueryTask) -> None:
    """执行浏览器查询（公共逻辑）"""
    task.status = ExpressQueryTaskStatus.QUERYING
    task.save(update_fields=["status", "updated_at"])

    # page.pdf 先写系统临时文件，再经 default_storage 保存到 media（文件名不可预测化）
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        tmp_pdf_path = Path(tmp_file.name)

    try:
        browser_service = ExpressBrowserQueryService()
        coro = browser_service.query_and_save_pdf(
            carrier_type=task.carrier_type,
            tracking_number=task.tracking_number,
            output_pdf=tmp_pdf_path,
        )

        # 在协程内部完成查询后主动关闭 Playwright 连接，避免 asyncio.run() 销毁循环后
        # Playwright 的 BaseSubprocessTransport.__del__ 触发 "Event loop is closed" 错误
        async def _run_and_cleanup() -> str:
            try:
                result = await coro
                return result
            finally:
                await ExpressBrowserQueryService.disconnect_playwright()

        # Django-Q2 worker 没有运行中的事件循环，直接用 asyncio.run()
        final_url = asyncio.run(_run_and_cleanup())
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
