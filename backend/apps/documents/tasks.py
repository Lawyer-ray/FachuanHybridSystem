"""Module for tasks."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.documents")


def merge_evidence_pdf_task(list_id: int) -> Any:
    from apps.documents.services.evidence.evidence_merge_usecase import EvidenceMergeUseCase

    logger.info("merge_evidence_pdf_task_start", extra={"list_id": list_id})
    result = EvidenceMergeUseCase().merge(list_id=list_id)
    logger.info("merge_evidence_pdf_task_done", extra={"list_id": list_id, "status": result.get("status")})
    return result
