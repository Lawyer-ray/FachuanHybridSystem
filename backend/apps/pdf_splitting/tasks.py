from __future__ import annotations

import logging
from uuid import UUID

from django.utils import timezone

from apps.core.services.storage_service import normalize_to_media_rel
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitMode, PdfSplitStage
from apps.pdf_splitting.services import PdfSplitJobService, PdfSplitService
from apps.pdf_splitting.services.storage import PdfSplitStorage

logger = logging.getLogger("apps.pdf_splitting")


def run_extract_stage(job_id: str) -> None:  # pragma: no cover
    """两阶段任务链 ①：只做取字，完成后把任务推进到分段阶段。

    独立成任务的理由：Django-Q 的 worker 超时（默认 600s）是整个任务的闐值。
    164 页实测取字 + 分段合起来会超时被杀（实测跑到 499s 就被杀），拆开
    后每段各有完整预算。取字产物落 pages.json + 逐页 OCR 缓存，
    即使第二阶段被杀也不用重跑云端。
    """
    from apps.pdf_splitting.services.split import two_stage

    job_uuid = UUID(job_id)
    split_service = PdfSplitService()
    try:
        job = PdfSplitJob.objects.get(id=job_uuid)
        job.refresh_from_db(fields=["cancel_requested", "split_mode"])
        if job.cancel_requested:
            PdfSplitJob.objects.filter(id=job.id).update(status=PdfSplitJobStatus.CANCELLED, finished_at=timezone.now())
            return

        pages, _summary = split_service.extract_stage(job)
        storage = PdfSplitStorage(job.id)
        two_stage.save_pages(storage, pages)
        job.refresh_from_db(fields=["progress", "total_pages"])
        two_stage.advance_to_segment_stage(job, pages_count=len(pages))
    except Exception as exc:
        logger.exception("pdf_split_extract_stage_failed", extra={"job_id": job_id})
        two_stage.mark_stage_failed(job_uuid, PdfSplitStage.EXTRACT, str(exc))


def run_segment_stage(job_id: str) -> None:  # pragma: no cover
    """两阶段任务链 ②：从 pages.json 读回取字结果，只做分段与落库。"""
    from apps.pdf_splitting.services.split import two_stage

    job_uuid = UUID(job_id)
    split_service = PdfSplitService()
    try:
        job = PdfSplitJob.objects.get(id=job_uuid)
        job.refresh_from_db(fields=["cancel_requested"])
        if job.cancel_requested:
            PdfSplitJob.objects.filter(id=job.id).update(status=PdfSplitJobStatus.CANCELLED)
            return

        split_service.segment_stage(job)
    except Exception as exc:
        logger.exception("pdf_split_segment_stage_failed", extra={"job_id": job_id})
        two_stage.mark_stage_failed(job_uuid, PdfSplitStage.SEGMENT, str(exc))


def execute_pdf_split_job(job_id: str) -> None:  # pragma: no cover
    job_service = PdfSplitJobService()
    split_service = PdfSplitService()
    job_uuid = UUID(job_id)
    try:
        job = job_service.get_job(job_uuid)
        job.refresh_from_db(fields=["split_mode"])
        # 手动拆分模式跳过后台分析，直接进入待复核状态
        if job.split_mode == PdfSplitMode.MANUAL_SPLIT:
            PdfSplitJob.objects.filter(id=job.id).update(
                status=PdfSplitJobStatus.REVIEW_REQUIRED,
                progress=100,
            )
            return
        split_service.analyze_job(job)
        job.refresh_from_db(fields=["split_mode", "status", "cancel_requested"])
        if (
            job.split_mode == PdfSplitMode.PAGE_SPLIT
            and job.status == PdfSplitJobStatus.REVIEW_REQUIRED
            and not job.cancel_requested
        ):
            split_service.export_job(job)
            storage = PdfSplitStorage(job.id)
            job.refresh_from_db(fields=["status", "cancel_requested"])
            if job.cancel_requested:
                return
            job_service.mark_completed(
                job_id=job_uuid,
                export_zip_relpath=normalize_to_media_rel(storage.export_zip_path.as_posix()),
            )
    except Exception as exc:
        logger.exception("pdf_split_job_failed", extra={"job_id": job_id})
        job_service.mark_failed(job_id=job_uuid, error_message=str(exc))


def export_pdf_split_job(job_id: str) -> None:  # pragma: no cover
    job_service = PdfSplitJobService()
    split_service = PdfSplitService()
    job_uuid = UUID(job_id)
    try:
        job = job_service.get_job(job_uuid)
        split_service.export_job(job)
        storage = PdfSplitStorage(job.id)
        job.refresh_from_db(fields=["status", "cancel_requested"])
        if job.cancel_requested:
            return
        job_service.mark_completed(
            job_id=job_uuid, export_zip_relpath=normalize_to_media_rel(storage.export_zip_path.as_posix())
        )
    except Exception as exc:
        logger.exception("pdf_split_export_failed", extra={"job_id": job_id})
        job_service.mark_failed(job_id=job_uuid, error_message=str(exc))
