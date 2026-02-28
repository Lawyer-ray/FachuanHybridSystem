"""Module for tasks."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.documents")


def merge_evidence_pdf_task(list_id: int) -> Any:
    # 已迁移到 apps.evidence.tasks，此处保留向后兼容
    from apps.evidence.tasks import merge_evidence_pdf_task as _task

    return _task(list_id)
