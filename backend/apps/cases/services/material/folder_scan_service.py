"""案件文件夹自动捕获服务。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case, CaseFolderBinding, CaseFolderScanSession, CaseFolderScanStatus
from apps.cases.services.log.caselog_service import CaseLogService
from apps.core.dependencies.core import build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.bound_folder_scan_service import BoundFolderScanService

logger = logging.getLogger(__name__)


class CaseFolderScanService:
    """案件自动捕获扫描、轮询、导入附件服务。"""

    _ACTIVE_STATUSES = {
        CaseFolderScanStatus.PENDING,
        CaseFolderScanStatus.RUNNING,
        CaseFolderScanStatus.CLASSIFYING,
    }

    def __init__(self, *, scan_service: BoundFolderScanService | None = None) -> None:
        self._scan_service = scan_service or BoundFolderScanService()
        self._case_log_service = CaseLogService()

    def start_scan(self, *, case_id: int, started_by: Any | None, rescan: bool = False) -> CaseFolderScanSession:
        self._ensure_case_exists(case_id)
        binding = self._get_accessible_binding(case_id)

        if not rescan:
            existing = (
                CaseFolderScanSession.objects.filter(case_id=case_id, status__in=self._ACTIVE_STATUSES)
                .order_by("-created_at")
                .first()
            )
            if existing:
                return existing

        session = CaseFolderScanSession.objects.create(
            case_id=case_id,
            status=CaseFolderScanStatus.PENDING,
            progress=0,
            current_file="",
            result_payload={"summary": {}, "candidates": []},
            started_by=started_by if getattr(started_by, "is_authenticated", False) else None,
        )

        task_id = build_task_submission_service().submit(
            "apps.cases.services.material.folder_scan_service.run_case_folder_scan_task",
            args=[str(session.id)],
            task_name=f"case_folder_scan_{session.id}",
        )

        CaseFolderScanSession.objects.filter(id=session.id).update(
            status=CaseFolderScanStatus.RUNNING,
            task_id=str(task_id),
            updated_at=timezone.now(),
        )
        session.refresh_from_db()
        logger.info("case_folder_scan_submitted", extra={"case_id": case_id, "session_id": str(session.id)})

        _ = binding
        return session

    def get_session(self, *, case_id: int, session_id: UUID) -> CaseFolderScanSession:
        try:
            return CaseFolderScanSession.objects.get(id=session_id, case_id=case_id)
        except CaseFolderScanSession.DoesNotExist:
            raise NotFoundError(_("扫描会话不存在")) from None

    def build_status_payload(self, *, session: CaseFolderScanSession) -> dict[str, Any]:
        payload = dict(session.result_payload or {})
        summary = payload.get("summary") or {}
        candidates = payload.get("candidates") or []
        stage_result = payload.get("stage_result") or {}
        prefill_map = stage_result.get("prefill_map") or {}

        return {
            "session_id": str(session.id),
            "status": session.status,
            "progress": int(session.progress or 0),
            "current_file": session.current_file or "",
            "summary": {
                "total_files": int(summary.get("total_files", 0) or 0),
                "deduped_files": int(summary.get("deduped_files", 0) or 0),
                "classified_files": int(summary.get("classified_files", 0) or 0),
            },
            "candidates": candidates,
            "error_message": session.error_message or "",
            "prefill_map": prefill_map,
        }

    @transaction.atomic
    def stage_to_attachments(
        self,
        *,
        case_id: int,
        session_id: UUID,
        items: list[dict[str, Any]],
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> dict[str, Any]:
        session = self.get_session(case_id=case_id, session_id=session_id)
        if session.status not in {CaseFolderScanStatus.COMPLETED, CaseFolderScanStatus.STAGED}:
            raise ValidationException(message=_("扫描尚未完成"), errors={"status": session.status})

        payload = dict(session.result_payload or {})
        candidates = payload.get("candidates") or []
        candidate_map = {str(item.get("source_path") or ""): item for item in candidates}

        selected_items = [item for item in items if bool(item.get("selected", True))]
        if not selected_items:
            raise ValidationException(message=_("未找到可导入的 PDF"))

        log = self._case_log_service.create_log(
            case_id=case_id,
            content=str(_("自动捕获材料")),
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

        uploads: list[SimpleUploadedFile] = []
        prefill_entries: list[dict[str, str]] = []

        for item in selected_items:
            source_path = str(item.get("source_path") or "").strip()
            if not source_path or source_path not in candidate_map:
                raise ValidationException(message=_("候选文件不存在"), errors={"source_path": source_path})

            file_path = Path(source_path)
            if not file_path.exists() or not file_path.is_file():
                raise ValidationException(message=_("源文件不存在"), errors={"source_path": source_path})

            uploads.append(
                SimpleUploadedFile(
                    name=file_path.name,
                    content=file_path.read_bytes(),
                    content_type="application/pdf",
                )
            )

            category = str(item.get("category") or "").strip()
            if category not in {"party", "non_party"}:
                category = ""

            side = str(item.get("side") or "").strip()
            if category != "party" or side not in {"our", "opponent"}:
                side = ""

            prefill_entries.append(
                {
                    "category": category,
                    "side": side,
                    "type_name_hint": str(item.get("type_name_hint") or "").strip(),
                }
            )

        created_attachments = self._case_log_service.upload_attachments(
            log_id=log.id,
            files=uploads,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

        prefill_map: dict[str, dict[str, str]] = {}
        for attachment, prefill in zip(created_attachments, prefill_entries, strict=True):
            prefill_map[str(attachment.id)] = prefill

        materials_url = self._build_materials_url(case_id=case_id, session_id=session_id)
        stage_result = {
            "log_id": int(log.id),
            "attachment_ids": [int(att.id) for att in created_attachments],
            "prefill_map": prefill_map,
            "materials_url": materials_url,
            "staged_at": timezone.now().isoformat(),
        }

        payload["stage_result"] = stage_result

        CaseFolderScanSession.objects.filter(id=session.id).update(
            status=CaseFolderScanStatus.STAGED,
            progress=100,
            current_file="",
            result_payload=payload,
            error_message="",
            updated_at=timezone.now(),
        )

        return {
            "session_id": str(session.id),
            "status": CaseFolderScanStatus.STAGED,
            "log_id": int(log.id),
            "attachment_ids": [int(att.id) for att in created_attachments],
            "materials_url": materials_url,
            "prefill_map": prefill_map,
        }

    def run_scan_task(self, *, session_id: str) -> None:
        session = CaseFolderScanSession.objects.select_related("case").filter(id=session_id).first()
        if not session:
            logger.warning("case_folder_scan_session_missing", extra={"session_id": session_id})
            return

        try:
            binding = self._get_accessible_binding(session.case_id)

            def _progress(status: str, progress: int, current_file: str | None) -> None:
                mapped_status = CaseFolderScanStatus.RUNNING
                if status == "classifying":
                    mapped_status = CaseFolderScanStatus.CLASSIFYING
                elif status == "completed":
                    mapped_status = CaseFolderScanStatus.COMPLETED

                CaseFolderScanSession.objects.filter(id=session.id).update(
                    status=mapped_status,
                    progress=int(progress),
                    current_file=current_file or "",
                    updated_at=timezone.now(),
                )

            result = self._scan_service.scan_folder(
                folder_path=binding.folder_path,
                domain="case",
                progress_callback=_progress,
            )

            CaseFolderScanSession.objects.filter(id=session.id).update(
                status=CaseFolderScanStatus.COMPLETED,
                progress=100,
                current_file="",
                result_payload=result,
                error_message="",
                updated_at=timezone.now(),
            )
        except Exception as exc:
            logger.exception("case_folder_scan_failed", extra={"session_id": session_id})
            CaseFolderScanSession.objects.filter(id=session.id).update(
                status=CaseFolderScanStatus.FAILED,
                error_message=str(exc),
                updated_at=timezone.now(),
            )

    @staticmethod
    def _ensure_case_exists(case_id: int) -> None:
        if Case.objects.filter(id=case_id).exists():
            return
        raise NotFoundError(_("案件不存在"))

    @staticmethod
    def _get_accessible_binding(case_id: int) -> CaseFolderBinding:
        binding = CaseFolderBinding.objects.filter(case_id=case_id).first()
        if not binding:
            raise ValidationException(message=_("未绑定文件夹"), errors={"case_id": case_id})

        folder = Path(binding.folder_path)
        if not folder.exists() or not folder.is_dir():
            raise ValidationException(message=_("绑定文件夹不可访问"), errors={"folder_path": binding.folder_path})

        return binding

    @staticmethod
    def _build_materials_url(*, case_id: int, session_id: UUID) -> str:
        base = reverse("admin:cases_case_materials", args=[case_id])
        return f"{base}?{urlencode({'scan_session': str(session_id)})}"


def run_case_folder_scan_task(session_id: str) -> None:
    """Django-Q 任务入口。"""
    CaseFolderScanService().run_scan_task(session_id=session_id)
