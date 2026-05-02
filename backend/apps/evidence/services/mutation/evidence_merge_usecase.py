"""Business logic services."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.evidence.services.wiring import get_case_service

logger = logging.getLogger(__name__)


@dataclass
class MergeProgressReporter:
    list_id: int
    min_interval_seconds: float = 0.5

    _last_progress: int = -1
    _last_update_ts: float = 0.0

    def report(self, *, current: int, total: int, message: str) -> None:
        from apps.evidence.models import EvidenceList

        progress = int(current * 100 / total) if total else 0
        now_ts = time.time()
        if progress == self._last_progress and (now_ts - self._last_update_ts) < self.min_interval_seconds:
            return
        EvidenceList.objects.filter(pk=self.list_id).update(
            merge_progress=progress,
            merge_current=current,
            merge_total=total,
            merge_message=message,
            updated_at=timezone.now(),
        )
        self._last_progress = progress
        self._last_update_ts = now_ts


class EvidenceMergeUseCase:
    def merge(self, *, list_id: int, reporter: MergeProgressReporter | None = None) -> dict[str, Any]:
        from apps.evidence.models import EvidenceList, MergeStatus
        from apps.evidence.services.core.evidence_service import EvidenceService
        from apps.evidence.services.infrastructure.pdf_merge_service import PDFMergeService

        try:
            with transaction.atomic():
                evidence_list = EvidenceList.objects.select_for_update().select_related("case").get(pk=list_id)

                if evidence_list.merge_status == MergeStatus.COMPLETED and evidence_list.merged_pdf:
                    return {
                        "list_id": list_id,
                        "status": "success",
                        "total_pages": evidence_list.total_pages,
                        "pdf_path": getattr(evidence_list.merged_pdf, "path", ""),
                    }

                total_files = evidence_list.items.filter(file__isnull=False).exclude(file="").count()
                evidence_list.merge_status = MergeStatus.PROCESSING
                evidence_list.merge_started_at = timezone.now()
                evidence_list.merge_finished_at = None
                evidence_list.merge_error = ""
                evidence_list.merge_progress = 0
                evidence_list.merge_current = 0
                evidence_list.merge_total = total_files
                evidence_list.merge_message = str(_("准备合并"))
                evidence_list.save(
                    update_fields=[
                        "merge_status",
                        "merge_started_at",
                        "merge_finished_at",
                        "merge_error",
                        "merge_progress",
                        "merge_current",
                        "merge_total",
                        "merge_message",
                    ]
                )
        except EvidenceList.DoesNotExist:
            return {"list_id": list_id, "status": "failed", "error": "证据清单不存在"}

        progress_reporter = reporter or MergeProgressReporter(list_id=list_id)

        try:

            def on_progress(current: int, total: int, message: str) -> None:
                progress_reporter.report(current=current, total=total, message=message)

            pdf_service = PDFMergeService()
            pdf_path = pdf_service.merge_evidence_files(evidence_list, progress_callback=on_progress)

            evidence_list.refresh_from_db()

            evidence_service = EvidenceService(case_service=get_case_service())
            evidence_service.calculate_page_ranges(list_id)
            evidence_service.update_subsequent_lists_pages(evidence_list.case_id, evidence_list.order + 1)

            EvidenceList.objects.filter(pk=list_id).update(
                merge_status=MergeStatus.COMPLETED,
                merge_finished_at=timezone.now(),
                merge_progress=100,
                merge_current=total_files,
                merge_message=_("合并完成"),
                updated_at=timezone.now(),
            )

            return {
                "list_id": list_id,
                "status": "success",
                "total_pages": evidence_list.total_pages,
                "pdf_path": pdf_path,
            }
        except Exception as e:
            logger.exception("操作失败")
            EvidenceList.objects.filter(pk=list_id).update(
                merge_status=MergeStatus.FAILED,
                merge_error=str(e),
                merge_finished_at=timezone.now(),
                merge_message=_("合并失败"),
                updated_at=timezone.now(),
            )
            return {"list_id": list_id, "status": "failed", "error": str(e)}
