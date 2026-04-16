from __future__ import annotations

import logging
from uuid import UUID

from apps.batch_printing.models import BatchPrintJob, BatchPrintJobStatus
from apps.batch_printing.services.wiring import get_batch_print_job_service
from django.utils import timezone

logger = logging.getLogger("apps.batch_printing")


def execute_batch_print_job(job_id: str) -> None:
    job_uuid = UUID(job_id)
    service = get_batch_print_job_service()
    try:
        service.execute_job(job_id=job_uuid)
    except Exception as exc:
        logger.exception("batch_print_job_failed", extra={"job_id": job_id})
        BatchPrintJob.objects.filter(id=job_uuid).update(
            status=BatchPrintJobStatus.FAILED,
            error_message=str(exc)[:1000],
            finished_at=timezone.now(),
        )
