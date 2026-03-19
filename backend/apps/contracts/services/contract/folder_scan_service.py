"""合同文件夹自动捕获服务。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import (
    Contract,
    ContractFolderBinding,
    ContractFolderScanSession,
    ContractFolderScanStatus,
    FinalizedMaterial,
    MaterialCategory,
)
from apps.core.dependencies.core import build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.bound_folder_scan_service import BoundFolderScanService

from .material_service import MaterialService

logger = logging.getLogger(__name__)


class ContractFolderScanService:
    """合同自动捕获扫描、轮询、确认导入服务。"""

    _ACTIVE_STATUSES = {
        ContractFolderScanStatus.PENDING,
        ContractFolderScanStatus.RUNNING,
        ContractFolderScanStatus.CLASSIFYING,
    }

    def __init__(self, *, scan_service: BoundFolderScanService | None = None) -> None:
        self._scan_service = scan_service or BoundFolderScanService()
        self._material_service = MaterialService()

    def start_scan(
        self,
        *,
        contract_id: int,
        started_by: Any | None,
        rescan: bool = False,
    ) -> ContractFolderScanSession:
        self._ensure_contract_exists(contract_id)
        binding = self._get_accessible_binding(contract_id)

        if not rescan:
            existing = (
                ContractFolderScanSession.objects.filter(contract_id=contract_id, status__in=self._ACTIVE_STATUSES)
                .order_by("-created_at")
                .first()
            )
            if existing:
                return existing

        session = ContractFolderScanSession.objects.create(
            contract_id=contract_id,
            status=ContractFolderScanStatus.PENDING,
            progress=0,
            current_file="",
            result_payload={"summary": {}, "candidates": []},
            started_by=started_by if getattr(started_by, "is_authenticated", False) else None,
        )

        task_id = build_task_submission_service().submit(
            "apps.contracts.services.contract.folder_scan_service.run_contract_folder_scan_task",
            args=[str(session.id)],
            task_name=f"contract_folder_scan_{session.id}",
        )

        ContractFolderScanSession.objects.filter(id=session.id).update(
            status=ContractFolderScanStatus.RUNNING,
            task_id=str(task_id),
            updated_at=timezone.now(),
        )
        session.refresh_from_db()
        logger.info("contract_folder_scan_submitted", extra={"contract_id": contract_id, "session_id": str(session.id)})

        _ = binding  # keep reference for validation side-effect
        return session

    def get_session(self, *, contract_id: int, session_id: UUID) -> ContractFolderScanSession:
        try:
            return ContractFolderScanSession.objects.get(id=session_id, contract_id=contract_id)
        except ContractFolderScanSession.DoesNotExist:
            raise NotFoundError(_("扫描会话不存在")) from None

    def build_status_payload(self, *, session: ContractFolderScanSession) -> dict[str, Any]:
        payload = dict(session.result_payload or {})
        summary = payload.get("summary") or {}
        candidates = payload.get("candidates") or []

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
        }

    @transaction.atomic
    def confirm_import(
        self,
        *,
        contract_id: int,
        session_id: UUID,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        session = self.get_session(contract_id=contract_id, session_id=session_id)
        if session.status not in {ContractFolderScanStatus.COMPLETED, ContractFolderScanStatus.IMPORTED}:
            raise ValidationException(message=_("扫描尚未完成"), errors={"status": session.status})

        payload = dict(session.result_payload or {})
        candidates = payload.get("candidates") or []
        candidate_map = {str(item.get("source_path") or ""): item for item in candidates}

        imported_count = 0
        for item in items:
            if not bool(item.get("selected", True)):
                continue

            source_path = str(item.get("source_path") or "").strip()
            if not source_path or source_path not in candidate_map:
                raise ValidationException(message=_("候选文件不存在"), errors={"source_path": source_path})

            category = str(item.get("category") or "other").strip()
            if category not in {MaterialCategory.CONTRACT_ORIGINAL, MaterialCategory.SUPPLEMENTARY_AGREEMENT, MaterialCategory.OTHER}:
                category = MaterialCategory.OTHER

            file_path = Path(source_path)
            if not file_path.exists() or not file_path.is_file():
                raise ValidationException(message=_("源文件不存在"), errors={"source_path": source_path})

            upload = SimpleUploadedFile(
                name=file_path.name,
                content=file_path.read_bytes(),
                content_type="application/pdf",
            )
            rel_path, original_name = self._material_service.save_material_file(upload, contract_id)
            FinalizedMaterial.objects.create(
                contract_id=contract_id,
                file_path=rel_path,
                original_filename=original_name,
                category=category,
            )
            imported_count += 1

        payload["import_result"] = {
            "imported_count": imported_count,
            "imported_at": timezone.now().isoformat(),
        }

        ContractFolderScanSession.objects.filter(id=session.id).update(
            status=ContractFolderScanStatus.IMPORTED,
            progress=100,
            current_file="",
            result_payload=payload,
            error_message="",
            updated_at=timezone.now(),
        )

        return {
            "session_id": str(session.id),
            "status": ContractFolderScanStatus.IMPORTED,
            "imported_count": imported_count,
        }

    def run_scan_task(self, *, session_id: str) -> None:
        session = ContractFolderScanSession.objects.select_related("contract").filter(id=session_id).first()
        if not session:
            logger.warning("contract_folder_scan_session_missing", extra={"session_id": session_id})
            return

        try:
            binding = self._get_accessible_binding(session.contract_id)

            def _progress(status: str, progress: int, current_file: str | None) -> None:
                mapped_status = ContractFolderScanStatus.RUNNING
                if status == "classifying":
                    mapped_status = ContractFolderScanStatus.CLASSIFYING
                elif status == "completed":
                    mapped_status = ContractFolderScanStatus.COMPLETED

                ContractFolderScanSession.objects.filter(id=session.id).update(
                    status=mapped_status,
                    progress=int(progress),
                    current_file=current_file or "",
                    updated_at=timezone.now(),
                )

            result = self._scan_service.scan_folder(
                folder_path=binding.folder_path,
                domain="contract",
                progress_callback=_progress,
            )

            ContractFolderScanSession.objects.filter(id=session.id).update(
                status=ContractFolderScanStatus.COMPLETED,
                progress=100,
                current_file="",
                result_payload=result,
                error_message="",
                updated_at=timezone.now(),
            )
        except Exception as exc:
            logger.exception("contract_folder_scan_failed", extra={"session_id": session_id})
            ContractFolderScanSession.objects.filter(id=session.id).update(
                status=ContractFolderScanStatus.FAILED,
                error_message=str(exc),
                updated_at=timezone.now(),
            )

    @staticmethod
    def _ensure_contract_exists(contract_id: int) -> None:
        if Contract.objects.filter(id=contract_id).exists():
            return
        raise NotFoundError(_("合同不存在"))

    @staticmethod
    def _get_accessible_binding(contract_id: int) -> ContractFolderBinding:
        binding = ContractFolderBinding.objects.filter(contract_id=contract_id).first()
        if not binding:
            raise ValidationException(message=_("未绑定文件夹"), errors={"contract_id": contract_id})

        folder = Path(binding.folder_path)
        if not folder.exists() or not folder.is_dir():
            raise ValidationException(message=_("绑定文件夹不可访问"), errors={"folder_path": binding.folder_path})

        return binding


def run_contract_folder_scan_task(session_id: str) -> None:
    """Django-Q 任务入口。"""
    ContractFolderScanService().run_scan_task(session_id=session_id)
