"""案件文件夹自动捕获服务。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
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

    def start_scan(
        self,
        *,
        case_id: int,
        started_by: Any | None,
        rescan: bool = False,
        scan_subfolder: str = "",
        enable_recognition: bool = False,
    ) -> CaseFolderScanSession:
        self._ensure_case_exists(case_id)
        binding = self._get_accessible_binding(case_id)
        scan_scope = self._resolve_scan_scope(binding.folder_path, scan_subfolder)
        scan_options = {"enable_recognition": bool(enable_recognition)}

        if not rescan:
            existing = (
                CaseFolderScanSession.objects.filter(case_id=case_id, status__in=self._ACTIVE_STATUSES)
                .order_by("-created_at")
                .first()
            )
            if existing:
                existing_subfolder = self._extract_scan_subfolder(existing.result_payload)
                existing_enable_recognition = self._extract_enable_recognition(existing.result_payload)
                if (
                    existing_subfolder == scan_scope["scan_subfolder"]
                    and existing_enable_recognition == scan_options["enable_recognition"]
                ):
                    return existing
                raise ValidationException(
                    message=_("已有进行中的扫描任务，请等待完成或使用“重新扫描”"),
                    errors={"session_id": str(existing.id)},
                )

        session = CaseFolderScanSession.objects.create(
            case_id=case_id,
            status=CaseFolderScanStatus.PENDING,
            progress=0,
            current_file="",
            result_payload={
                "summary": {},
                "candidates": [],
                "scan_scope": scan_scope,
                "scan_options": scan_options,
            },
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
        logger.info(
            "case_folder_scan_submitted",
            extra={
                "case_id": case_id,
                "session_id": str(session.id),
                "scan_subfolder": scan_scope["scan_subfolder"],
                "enable_recognition": scan_options["enable_recognition"],
            },
        )
        return session

    def list_scan_subfolders(self, *, case_id: int) -> dict[str, Any]:
        self._ensure_case_exists(case_id)
        binding = self._get_accessible_binding(case_id)
        root = Path(binding.folder_path).expanduser().resolve()

        subfolders: list[dict[str, str]] = []
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if child.name.startswith("."):
                continue
            if not child.is_dir():
                continue
            resolved_child = child.resolve()
            if not self._is_within_root(root, resolved_child):
                continue
            subfolders.append(
                {
                    "relative_path": child.name,
                    "display_name": child.name,
                }
            )

        return {
            "root_path": root.as_posix(),
            "subfolders": subfolders,
        }

    def get_session(self, *, case_id: int, session_id: UUID) -> CaseFolderScanSession:
        try:
            return CaseFolderScanSession.objects.get(id=session_id, case_id=case_id)
        except CaseFolderScanSession.DoesNotExist:
            raise NotFoundError(_("扫描会话不存在")) from None

    def build_status_payload(self, *, session: CaseFolderScanSession) -> dict[str, Any]:
        payload = dict(session.result_payload or {})
        summary = payload.get("summary") or {}
        candidates = self._normalize_candidates_for_scan_scope(payload.get("candidates") or [], payload)
        stage_result = payload.get("stage_result") or {}
        prefill_map = stage_result.get("prefill_map") or {}
        scan_subfolder = self._extract_scan_subfolder(payload)
        enable_recognition = self._extract_enable_recognition(payload)

        return {
            "session_id": str(session.id),
            "status": session.status,
            "progress": int(session.progress or 0),
            "current_file": session.current_file or "",
            "scan_subfolder": scan_subfolder,
            "enable_recognition": enable_recognition,
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
        prefill_entries: list[dict[str, Any]] = []

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

            supervising_authority_id: int | None = None
            if category == "non_party":
                supervising_authority_id = self._to_int(item.get("supervising_authority_id"))

            party_ids: list[int] = []
            if category == "party":
                raw_party_ids = item.get("party_ids") or []
                if isinstance(raw_party_ids, list):
                    seen_party_ids: set[int] = set()
                    for raw_pid in raw_party_ids:
                        pid = self._to_int(raw_pid)
                        if pid and pid not in seen_party_ids:
                            seen_party_ids.add(pid)
                            party_ids.append(pid)

            prefill_entries.append(
                {
                    "category": category,
                    "side": side,
                    "type_name_hint": str(item.get("type_name_hint") or "").strip(),
                    "supervising_authority_id": supervising_authority_id,
                    "party_ids": party_ids,
                }
            )

        created_attachments = self._case_log_service.upload_attachments(
            log_id=log.id,
            files=uploads,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

        prefill_map: dict[str, dict[str, Any]] = {}
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
            payload = dict(session.result_payload or {})
            scan_scope = self._resolve_scan_scope(
                binding.folder_path,
                self._extract_scan_subfolder(payload),
            )
            enable_recognition = self._extract_enable_recognition(payload)
            classification_context = self._build_classification_context(session.case)

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
                folder_path=scan_scope["scan_folder"],
                domain="case",
                progress_callback=_progress,
                enable_recognition=enable_recognition,
                classification_context=classification_context,
            )
            result["scan_scope"] = scan_scope
            result["scan_options"] = {"enable_recognition": enable_recognition}

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

    def _extract_scan_subfolder(self, payload: dict[str, Any] | None) -> str:
        scope = (payload or {}).get("scan_scope") or {}
        return str(scope.get("scan_subfolder") or "").strip()

    def _normalize_candidates_for_scan_scope(
        self,
        candidates: list[dict[str, Any]],
        payload: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        if not self._should_force_our_party_for_filing_materials(payload):
            return candidates

        normalized: list[dict[str, Any]] = []
        for item in candidates:
            candidate = dict(item or {})
            candidate["suggested_category"] = "party"
            candidate["suggested_side"] = "our"
            if not str(candidate.get("reason") or "").strip():
                candidate["reason"] = "命中目录规则：立案材料目录默认归类为我方当事人材料"
            normalized.append(candidate)
        return normalized

    def _should_force_our_party_for_filing_materials(self, payload: dict[str, Any] | None) -> bool:
        scope = (payload or {}).get("scan_scope") or {}
        scan_subfolder = str(scope.get("scan_subfolder") or "").strip()
        scan_folder = str(scope.get("scan_folder") or "").strip()
        return ("立案材料" in scan_subfolder) or ("立案材料" in scan_folder)

    def _extract_enable_recognition(self, payload: dict[str, Any] | None) -> bool:
        options = (payload or {}).get("scan_options") or {}
        if "enable_recognition" not in options:
            return True
        return bool(options.get("enable_recognition"))

    def _resolve_scan_scope(self, root_folder: str, scan_subfolder: str) -> dict[str, str]:
        root = Path(root_folder).expanduser().resolve()
        normalized_subfolder = self._normalize_scan_subfolder(scan_subfolder)

        scan_path = root
        if normalized_subfolder:
            scan_path = (root / normalized_subfolder).resolve()
            if not self._is_within_root(root, scan_path):
                raise ValidationException(
                    message=_("扫描子文件夹越界"),
                    errors={"scan_subfolder": normalized_subfolder},
                )
            if not scan_path.exists() or not scan_path.is_dir():
                raise ValidationException(
                    message=_("扫描子文件夹不可访问"),
                    errors={"scan_subfolder": normalized_subfolder},
                )

        return {
            "root_folder": root.as_posix(),
            "scan_folder": scan_path.as_posix(),
            "scan_subfolder": normalized_subfolder,
        }

    def _normalize_scan_subfolder(self, scan_subfolder: str) -> str:
        raw = str(scan_subfolder or "").strip().replace("\\", "/")
        if not raw:
            return ""
        if raw.startswith("/") or raw.startswith("~") or re.match(r"^[A-Za-z]:/", raw):
            raise ValidationException(message=_("扫描子文件夹必须使用相对路径"), errors={"scan_subfolder": raw})

        parts = [part for part in raw.split("/") if part not in {"", "."}]
        if not parts:
            return ""
        if any(part == ".." for part in parts):
            raise ValidationException(message=_("扫描子文件夹路径非法"), errors={"scan_subfolder": raw})
        return "/".join(parts)

    def _is_within_root(self, root: Path, target: Path) -> bool:
        try:
            return os.path.commonpath([root.as_posix(), target.as_posix()]) == root.as_posix()
        except ValueError:
            return False

    def _build_classification_context(self, case: Case) -> dict[str, Any]:
        our_party_ids: list[int] = []
        opponent_party_ids: list[int] = []
        our_party_names: list[str] = []
        opponent_party_names: list[str] = []

        for party in case.parties.select_related("client").all():
            client = getattr(party, "client", None)
            if not client:
                continue
            party_id = int(getattr(party, "id", 0) or 0)
            party_name = str(getattr(client, "name", "") or "").strip()
            is_our = bool(getattr(client, "is_our_client", False))
            if is_our:
                if party_id:
                    our_party_ids.append(party_id)
                if party_name:
                    our_party_names.append(party_name)
            else:
                if party_id:
                    opponent_party_ids.append(party_id)
                if party_name:
                    opponent_party_names.append(party_name)

        authority_ids = [int(auth.id) for auth in case.supervising_authorities.all()]
        primary_authority_id = authority_ids[0] if authority_ids else None

        return {
            "our_party_ids": our_party_ids,
            "opponent_party_ids": opponent_party_ids,
            "our_party_names": our_party_names,
            "opponent_party_names": opponent_party_names,
            "supervising_authority_ids": authority_ids,
            "primary_supervising_authority_id": primary_authority_id,
        }

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        if parsed <= 0:
            return None
        return parsed

    @staticmethod
    def _build_materials_url(*, case_id: int, session_id: UUID) -> str:
        base = reverse("admin:cases_case_materials", args=[case_id])
        return f"{base}?{urlencode({'scan_session': str(session_id)})}"


def run_case_folder_scan_task(session_id: str) -> None:
    """Django-Q 任务入口。"""
    CaseFolderScanService().run_scan_task(session_id=session_id)
