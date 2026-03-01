"""证据模块异步任务"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.evidence")


def merge_evidence_pdf_task(list_id: int) -> Any:
    from apps.evidence.services.evidence_merge_usecase import EvidenceMergeUseCase

    logger.info("merge_evidence_pdf_task_start", extra={"list_id": list_id})
    result = EvidenceMergeUseCase().merge(list_id=list_id)
    logger.info("merge_evidence_pdf_task_done", extra={"list_id": list_id, "status": result.get("status")})
    return result


def ocr_evidence_item_task(item_id: int) -> None:
    """异步 OCR 提取证据文件文本"""
    from apps.evidence.services.evidence_ocr_service import EvidenceOCRService

    logger.info("ocr_evidence_item_start", extra={"item_id": item_id})
    EvidenceOCRService().extract_and_save(item_id)
    logger.info("ocr_evidence_item_done", extra={"item_id": item_id})
