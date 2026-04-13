from __future__ import annotations

import logging
from uuid import UUID

from apps.core.services.storage_service import normalize_to_media_rel
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitMode
from apps.pdf_splitting.services import PdfSplitJobService, PdfSplitService
from apps.pdf_splitting.services.storage import PdfSplitStorage

logger = logging.getLogger("apps.pdf_splitting")


def execute_pdf_split_job(job_id: str) -> None:
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


def export_pdf_split_job(job_id: str) -> None:
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
