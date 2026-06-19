"""合同文件夹自动捕获服务。"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.contracts.models import (
    Contract,
    ContractFolderBinding,
    ContractFolderScanSession,
    ContractFolderScanStatus,
)
from apps.contracts.services.archive.category_mapping import get_archive_category
from apps.contracts.services.contract.integrations.archive_classifier import (
    collect_archive_item_options,
    collect_work_log_suggestions,
)
from apps.core.dependencies.core import build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.bound_folder_scan_service import BoundFolderScanService

from ._candidate_post_processor import CandidatePostProcessor
from ._import_pipeline import ImportPipeline

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
        self._post_processor = CandidatePostProcessor(self._scan_service)
        self._import_pipeline = ImportPipeline()

    # ── Public API ──────────────────────────────────────────────────────

    def start_scan(
        self,
        *,
        contract_id: int,
        started_by: Any | None,
        rescan: bool = False,
        scan_subfolder: str = "",
    ) -> ContractFolderScanSession:  # pragma: no cover
        self._ensure_contract_exists(contract_id)
        binding = self._get_accessible_binding(contract_id)
        storage_provider = self._make_provider_for_binding(binding)
        scan_scope = self._resolve_scan_scope(binding.folder_path, scan_subfolder, storage_provider=storage_provider)

        if not rescan:
            existing = (
                ContractFolderScanSession.objects.filter(contract_id=contract_id, status__in=self._ACTIVE_STATUSES)
                .order_by("-created_at")
                .first()
            )
            if existing:
                existing_subfolder = self._extract_scan_subfolder(existing.result_payload)
                if existing_subfolder == scan_scope["scan_subfolder"]:
                    return existing
                raise ValidationException(
                    message="已有进行中的扫描任务，请等待完成或使用“重新扫描”",
                    errors={"session_id": str(existing.id)},
                )

            # 复用同子文件夹的已完成会话，避免重复扫描
            completed_match = (
                ContractFolderScanSession.objects.filter(
                    contract_id=contract_id,
                    status=ContractFolderScanStatus.COMPLETED,
                )
                .order_by("-created_at")
                .first()
            )
            if completed_match:
                completed_subfolder = self._extract_scan_subfolder(completed_match.result_payload)
                if completed_subfolder == scan_scope["scan_subfolder"]:
                    return completed_match

        session = ContractFolderScanSession.objects.create(
            contract_id=contract_id,
            status=ContractFolderScanStatus.PENDING,
            progress=0,
            current_file="",
            result_payload={
                "summary": {},
                "candidates": [],
                "scan_scope": scan_scope,
            },
            started_by=started_by if getattr(started_by, "is_authenticated", False) else None,
        )

        task_id = build_task_submission_service().submit(
            "apps.contracts.services.contract.integrations.folder_scan_service.run_contract_folder_scan_task",
            args=[str(session.id)],
            task_name=f"contract_folder_scan_{session.id}",
        )

        ContractFolderScanSession.objects.filter(id=session.id).update(
            status=ContractFolderScanStatus.RUNNING,
            task_id=str(task_id),
            updated_at=timezone.now(),
        )
        session.refresh_from_db()
        logger.info(
            "contract_folder_scan_submitted",
            extra={
                "contract_id": contract_id,
                "session_id": str(session.id),
                "scan_subfolder": scan_scope["scan_subfolder"],
            },
        )
        return session

    def list_scan_subfolders(self, *, contract_id: int) -> dict[str, Any]:  # pragma: no cover
        self._ensure_contract_exists(contract_id)
        binding = self._get_accessible_binding(contract_id)

        # Cloud storage: use provider to list subdirectories
        storage_type = getattr(binding, "storage_type", "local")
        if storage_type != "local":
            provider = self._make_provider_for_binding(binding)
            root_path = binding.folder_path
            try:
                children = provider.list_directory(root_path) if provider else []
            except Exception:
                children = []
            subfolders = []
            for child in children:
                if not child.is_dir:
                    continue
                if child.name.startswith("."):
                    continue
                subfolders.append({"relative_path": child.name, "display_name": child.name})
            subfolders.sort(key=lambda x: x["display_name"].lower())
            return {"root_path": root_path, "subfolders": subfolders}

        # Local filesystem
        root = Path(binding.folder_path).expanduser().resolve()

        subfolders_local: list[dict[str, str]] = []
        for child_local in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if child_local.name.startswith("."):
                continue
            if not child_local.is_dir():
                continue
            resolved_child = child_local.resolve()
            if not self._is_within_root(root, resolved_child):
                continue
            subfolders_local.append(
                {
                    "relative_path": child_local.name,
                    "display_name": child_local.name,
                }
            )

        return {
            "root_path": root.as_posix(),
            "subfolders": subfolders_local,
        }

    def get_session(self, *, contract_id: int, session_id: UUID) -> ContractFolderScanSession:
        try:
            return ContractFolderScanSession.objects.get(id=session_id, contract_id=contract_id)
        except ContractFolderScanSession.DoesNotExist:
            raise NotFoundError("扫描会话不存在") from None

    def get_latest_session(self, *, contract_id: int) -> ContractFolderScanSession | None:  # pragma: no cover
        """返回合同最新的扫描会话，没有则返回 None。"""
        return ContractFolderScanSession.objects.filter(contract_id=contract_id).order_by("-created_at").first()

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
            "archive_category": payload.get("archive_category") or "",
            "archive_item_options": payload.get("archive_item_options") or [],
            "work_log_suggestions": payload.get("work_log_suggestions") or [],
        }

    @transaction.atomic
    def confirm_import(
        self,
        *,
        contract_id: int,
        session_id: UUID,
        items: list[dict[str, Any]],
        work_log_suggestions: list[dict[str, str]] | None = None,
        storage_provider: Any | None = None,
    ) -> dict[str, Any]:  # pragma: no cover
        session = self.get_session(contract_id=contract_id, session_id=session_id)
        return self._import_pipeline.confirm_import(
            contract_id=contract_id,
            session=session,
            items=items,
            work_log_suggestions=work_log_suggestions,
            storage_provider=storage_provider,
            learn_from_correction_fn=self._learn_from_import_correction,
        )

    def run_scan_task(self, *, session_id: str) -> None:  # pragma: no cover
        session = ContractFolderScanSession.objects.select_related("contract").filter(id=session_id).first()
        if not session:
            logger.warning("contract_folder_scan_session_missing", extra={"session_id": session_id})
            return

        try:
            binding = self._get_accessible_binding(session.contract_id)
            storage_provider = self._make_provider_for_binding(binding)
            payload = dict(session.result_payload or {})
            scan_scope = self._resolve_scan_scope(
                binding.folder_path,
                self._extract_scan_subfolder(payload),
                storage_provider=storage_provider,
            )

            def _progress(status: str, progress: int, current_file: str | None) -> None:  # pragma: no cover
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
                folder_path=scan_scope["scan_folder"],
                domain="contract",
                progress_callback=_progress,
                storage_provider=storage_provider,
            )
            result["scan_scope"] = scan_scope

            contract = session.contract
            archive_category = get_archive_category(getattr(contract, "case_type", ""))

            candidates = result.get("candidates") or []
            candidates = self._post_processor.post_process_candidates(
                candidates=candidates,
                archive_category=archive_category,
                scan_folder=scan_scope["scan_folder"],
                contract_id=session.contract_id,
                storage_provider=storage_provider,
            )
            result["candidates"] = candidates

            # 工作日志建议
            work_log_suggestions = collect_work_log_suggestions(
                scan_scope["scan_folder"], archive_category, storage_provider=storage_provider
            )
            result["work_log_suggestions"] = work_log_suggestions

            # 归档清单项选项
            archive_item_options = collect_archive_item_options(archive_category)
            result["archive_item_options"] = archive_item_options
            result["archive_category"] = archive_category

            ContractFolderScanSession.objects.filter(id=session.id).update(
                status=ContractFolderScanStatus.COMPLETED,
                progress=100,
                current_file="",
                result_payload=result,
                error_message="",
                updated_at=timezone.now(),
            )
        except Exception as exc:
            from apps.core.cloud_storage.exceptions import CloudStorageError

            if isinstance(exc, CloudStorageError):
                error_msg = str(exc)
            else:
                error_msg = f"扫描失败: {type(exc).__name__}"
            logger.exception("contract_folder_scan_failed", extra={"session_id": session_id})
            ContractFolderScanSession.objects.filter(id=session.id).update(
                status=ContractFolderScanStatus.FAILED,
                error_message=error_msg,
                updated_at=timezone.now(),
            )

    # ── Private helpers ─────────────────────────────────────────────────

    def _ensure_contract_exists(self, contract_id: int) -> None:  # pragma: no cover
        if Contract.objects.filter(id=contract_id).exists():
            return
        raise NotFoundError("合同不存在")

    def _get_accessible_binding(self, contract_id: int) -> ContractFolderBinding:  # pragma: no cover
        binding = ContractFolderBinding.objects.filter(contract_id=contract_id).first()
        if not binding:
            raise ValidationException(message="未绑定文件夹", errors={"contract_id": contract_id})

        storage_type = getattr(binding, "storage_type", "local")
        if storage_type == "local":
            folder = Path(binding.folder_path)
            if not folder.exists() or not folder.is_dir():
                raise ValidationException(message="绑定文件夹不可访问", errors={"folder_path": binding.folder_path})
        else:
            # Cloud storage: use provider to check accessibility
            from apps.core.cloud_storage.factory import create_provider_for_binding

            provider = create_provider_for_binding(binding)
            try:
                accessible = provider.is_dir(binding.folder_path) or provider.exists(binding.folder_path)
            except Exception:
                accessible = False
            if not accessible:
                raise ValidationException(message="绑定文件夹不可访问", errors={"folder_path": binding.folder_path})

        return binding

    def _make_provider_for_binding(self, binding: ContractFolderBinding) -> Any | None:  # pragma: no cover
        """Create a cloud storage provider for the binding, or None for local."""
        storage_type = getattr(binding, "storage_type", "local")
        if storage_type == "local":
            return None
        from apps.core.cloud_storage.factory import create_provider_for_binding

        return create_provider_for_binding(binding)

    def _extract_scan_subfolder(self, payload: dict[str, Any] | None) -> str:
        scope = (payload or {}).get("scan_scope") or {}
        return str(scope.get("scan_subfolder") or "").strip()

    def _resolve_scan_scope(
        self,
        root_folder: str,
        scan_subfolder: str,
        storage_provider: Any | None = None,
    ) -> dict[str, str]:  # pragma: no cover
        normalized_subfolder = self._normalize_scan_subfolder(scan_subfolder)

        if storage_provider is not None:
            # Cloud storage: use PurePosixPath for path arithmetic
            from pathlib import PurePosixPath

            root = PurePosixPath(root_folder)
            scan_path = root
            if normalized_subfolder:
                scan_path = root / normalized_subfolder
                # Normalize to prevent traversal
                scan_path = PurePosixPath("/") / str(scan_path).lstrip("/")
                root_str = str(root)
                scan_str = str(scan_path)
                is_within = (
                    scan_str.startswith(root_str + "/")
                    or scan_str == root_str
                    or (root_str == "/" and scan_str.startswith("/") and scan_str != "/")
                )
                if not is_within:
                    raise ValidationException(
                        message="扫描子文件夹越界",
                        errors={"scan_subfolder": normalized_subfolder},
                    )
                if not storage_provider.exists(str(scan_path)):
                    raise ValidationException(
                        message="扫描子文件夹不可访问",
                        errors={"scan_subfolder": normalized_subfolder},
                    )

            return {
                "root_folder": str(root),
                "scan_folder": str(scan_path),
                "scan_subfolder": normalized_subfolder,
            }

        # Local filesystem
        root_local = Path(root_folder).expanduser().resolve()
        scan_path_local = root_local
        if normalized_subfolder:
            scan_path_local = (root_local / normalized_subfolder).resolve()
            if not self._is_within_root(root_local, scan_path_local):
                raise ValidationException(
                    message="扫描子文件夹越界",
                    errors={"scan_subfolder": normalized_subfolder},
                )
            if not scan_path_local.exists() or not scan_path_local.is_dir():
                raise ValidationException(
                    message="扫描子文件夹不可访问",
                    errors={"scan_subfolder": normalized_subfolder},
                )

        return {
            "root_folder": root_local.as_posix(),
            "scan_folder": scan_path_local.as_posix(),
            "scan_subfolder": normalized_subfolder,
        }

    def _normalize_scan_subfolder(self, scan_subfolder: str) -> str:
        raw = str(scan_subfolder or "").strip().replace("\\", "/")
        if not raw:
            return ""
        if raw.startswith("/") or raw.startswith("~") or re.match(r"^[A-Za-z]:/", raw):
            raise ValidationException(message="扫描子文件夹必须使用相对路径", errors={"scan_subfolder": raw})

        parts = [part for part in raw.split("/") if part not in {"", "."}]
        if not parts:
            return ""
        if any(part == ".." for part in parts):
            raise ValidationException(message="扫描子文件夹路径非法", errors={"scan_subfolder": raw})
        return "/".join(parts)

    def _is_within_root(self, root: Path, target: Path) -> bool:
        try:
            return os.path.commonpath([root.as_posix(), target.as_posix()]).replace("\\", "/") == root.as_posix()
        except ValueError:
            return False

    def _learn_from_import_correction(
        self,
        *,
        candidate: dict[str, Any],
        actual_archive_item_code: str,
        contract_id: int,
    ) -> None:
        """导入确认时自动学习：如果用户修改了 archive_item_code，记录为学习规则。"""
        if not actual_archive_item_code:
            return

        # 获取扫描时分类器预测的 archive_item_code
        predicted_code = str(candidate.get("archive_item_code") or "").strip()
        if predicted_code == actual_archive_item_code:
            return  # 用户没修改，无需学习

        # 只对案件材料学习
        if str(candidate.get("suggested_category") or "") != "case_material":
            return

        filename = str(candidate.get("filename") or "")
        if not filename:
            return

        try:
            from apps.contracts.models import ArchiveClassificationRule
            from apps.contracts.services.archive.category_mapping import get_archive_category
            from apps.contracts.services.archive.learning_service import (
                extract_keywords,
            )

            contract = Contract.objects.filter(id=contract_id).values_list("case_type", flat=True).first()
            if not contract:
                return
            archive_category = get_archive_category(contract)
            if not archive_category:
                return

            keywords = extract_keywords(filename)
            for kw in keywords:
                # 跳过歧义关键词：如果已有规则映射到不同 code，不覆盖
                existing = (
                    ArchiveClassificationRule.objects.filter(
                        archive_category=archive_category,
                        filename_keyword=kw,
                    )
                    .exclude(archive_item_code=actual_archive_item_code)
                    .first()
                )
                if existing:
                    continue

                ArchiveClassificationRule.objects.get_or_create(
                    archive_category=archive_category,
                    filename_keyword=kw,
                    defaults={
                        "archive_item_code": actual_archive_item_code,
                        "source": "manual",
                        "hit_count": 1,
                    },
                )
        except (OSError, RuntimeError, ValueError):
            logger.exception("learn_from_import_correction_failed")


def run_contract_folder_scan_task(session_id: str) -> None:  # pragma: no cover
    """Django-Q 任务入口。"""
    ContractFolderScanService().run_scan_task(session_id=session_id)


def _normalize_docx_name(filename: str) -> str:
    """标准化文件名用于关键词匹配。"""
    return re.sub(r"\s+", "", str(filename or "").strip().lower())
