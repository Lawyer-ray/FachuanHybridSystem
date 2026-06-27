"""案件文件夹自动捕获服务。"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.cases.models import Case, CaseFolderBinding, CaseFolderScanSession, CaseFolderScanStatus
from apps.cases.services.log.caselog_service import CaseLogService
from apps.core.dependencies.core import build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.bound_folder_scan_service import BoundFolderScanService

logger = logging.getLogger(__name__)


class CaseFolderScanService:
    """案件自动捕获扫描、轮询、导入附件服务。"""

    _FORCE_OUR_PARTY_FOLDER_KEYWORDS = (
        "立案材料",
        "递交给法院的资料",
        "提交给法院的资料",
    )
    _FORCE_OUR_PARTY_REASON = "命中目录规则：立案材料/提交给法院的资料目录默认归类为我方当事人材料"

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
    ) -> CaseFolderScanSession:  # pragma: no cover
        self._ensure_case_exists(case_id)
        binding = self._get_accessible_binding(case_id)
        storage_provider = self._make_provider_for_binding(binding)
        scan_scope = self._resolve_scan_scope(
            binding.resolved_folder_path, scan_subfolder, storage_provider=storage_provider
        )
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
                    message="已有进行中的扫描任务，请等待完成或使用“重新扫描”",
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

    def list_scan_subfolders(self, *, case_id: int) -> dict[str, Any]:  # pragma: no cover
        self._ensure_case_exists(case_id)
        binding = self._get_accessible_binding(case_id)

        # Cloud storage: use provider to list subdirectories
        storage_type = getattr(binding, "storage_type", "local")
        if storage_type != "local":
            from apps.core.cloud_storage.factory import create_provider_for_binding

            provider = create_provider_for_binding(binding)
            root_path = binding.resolved_folder_path
            try:
                children = provider.list_directory(root_path)
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
        root = Path(binding.resolved_folder_path).expanduser().resolve()

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

    def get_session(self, *, case_id: int, session_id: UUID) -> CaseFolderScanSession:
        try:
            return CaseFolderScanSession.objects.get(id=session_id, case_id=case_id)
        except CaseFolderScanSession.DoesNotExist:
            raise NotFoundError("扫描会话不存在") from None

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

    def stage_to_attachments(
        self,
        *,
        case_id: int,
        session_id: UUID,
        items: list[dict[str, Any]],
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> dict[str, Any]:  # pragma: no cover
        session = self.get_session(case_id=case_id, session_id=session_id)
        if session.status not in {CaseFolderScanStatus.COMPLETED, CaseFolderScanStatus.STAGED}:
            raise ValidationException(message="扫描尚未完成", errors={"status": session.status})

        payload = dict(session.result_payload or {})
        candidates = payload.get("candidates") or []
        candidate_map = {str(item.get("source_path") or ""): item for item in candidates}

        # 解析云存储 provider
        storage_provider = None
        try:
            from apps.cases.models.material import CaseFolderBinding

            binding = CaseFolderBinding.objects.filter(case_id=case_id).first()
            if binding and getattr(binding, "storage_type", "local") != "local":
                from apps.core.cloud_storage.factory import create_provider_for_binding

                storage_provider = create_provider_for_binding(binding)
        except Exception:
            pass

        selected_items = [item for item in items if bool(item.get("selected", True))]
        if not selected_items:
            raise ValidationException(message="未找到可导入的 PDF")

        # ── 在事务外完成所有文件 I/O ──────────────────────────────
        uploads, prefill_entries = self._read_files_for_staging(
            selected_items=selected_items,
            candidate_map=candidate_map,
            storage_provider=storage_provider,
        )

        # ── 事务内仅做 DB 写入 ────────────────────────────────────
        return self._write_staging_to_db(
            case_id=case_id,
            session_id=session_id,
            session=session,
            payload=payload,
            uploads=uploads,
            prefill_entries=prefill_entries,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def _read_files_for_staging(
        self,
        *,
        selected_items: list[dict[str, Any]],
        candidate_map: dict[str, Any],
        storage_provider: Any | None,
    ) -> tuple[list[SimpleUploadedFile], list[dict[str, Any]]]:
        """在事务外读取所有文件并构建 prefill 元数据。"""
        uploads: list[SimpleUploadedFile] = []
        prefill_entries: list[dict[str, Any]] = []

        for item in selected_items:
            source_path = str(item.get("source_path") or "").strip()
            if not source_path or source_path not in candidate_map:
                raise ValidationException(message="候选文件不存在", errors={"source_path": source_path})

            if storage_provider is not None:
                from pathlib import PurePosixPath

                from apps.core.cloud_storage.exceptions import CloudStorageError

                try:
                    file_bytes = storage_provider.read_file(source_path)
                except CloudStorageError:
                    raise
                except Exception as e:
                    raise CloudStorageError(
                        f"读取云存储文件失败: {source_path}",
                        provider="云存储",
                    ) from e
                file_name = PurePosixPath(source_path).name
            else:
                file_path = Path(source_path)
                if not file_path.exists() or not file_path.is_file():
                    raise ValidationException(message="源文件不存在", errors={"source_path": source_path})
                file_bytes = file_path.read_bytes()
                file_name = file_path.name

            uploads.append(
                SimpleUploadedFile(
                    name=file_name,
                    content=file_bytes,
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

        return uploads, prefill_entries

    @transaction.atomic
    def _write_staging_to_db(
        self,
        *,
        case_id: int,
        session_id: UUID,
        session: CaseFolderScanSession,
        payload: dict[str, Any],
        uploads: list[SimpleUploadedFile],
        prefill_entries: list[dict[str, Any]],
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> dict[str, Any]:
        """在事务内执行所有 DB 写入操作。"""
        log = self._case_log_service.create_log(
            case_id=case_id,
            content="自动捕获材料",
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

        created_attachments = self._case_log_service.upload_attachments(
            log_id=log.id,
            files=uploads,  # type: ignore[arg-type]
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

    def run_scan_task(self, *, session_id: str) -> None:  # pragma: no cover
        session = (
            CaseFolderScanSession.objects.select_related("case")
            .prefetch_related("case__parties__client", "case__supervising_authorities")
            .filter(id=session_id)
            .first()
        )
        if not session:
            logger.warning("case_folder_scan_session_missing", extra={"session_id": session_id})
            return

        try:
            binding = self._get_accessible_binding(session.case_id)
            storage_provider = self._make_provider_for_binding(binding)
            payload = dict(session.result_payload or {})
            scan_scope = self._resolve_scan_scope(
                binding.resolved_folder_path,
                self._extract_scan_subfolder(payload),
                storage_provider=storage_provider,
            )
            enable_recognition = self._extract_enable_recognition(payload)
            classification_context = self._build_classification_context(session.case)

            def _progress(status: str, progress: int, current_file: str | None) -> None:  # pragma: no cover
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
                scan_subfolder=scan_scope["scan_subfolder"],
                storage_provider=storage_provider,
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
            from apps.core.cloud_storage.exceptions import CloudStorageError

            if isinstance(exc, CloudStorageError):
                error_msg = str(exc)
            else:
                error_msg = f"扫描失败: {type(exc).__name__}"
            logger.exception("case_folder_scan_failed", extra={"session_id": session_id})
            CaseFolderScanSession.objects.filter(id=session.id).update(
                status=CaseFolderScanStatus.FAILED,
                error_message=error_msg,
                updated_at=timezone.now(),
            )

    @staticmethod
    def _ensure_case_exists(case_id: int) -> None:
        if Case.objects.filter(id=case_id).exists():
            return
        raise NotFoundError("案件不存在")

    @staticmethod
    def _get_accessible_binding(case_id: int) -> CaseFolderBinding:
        binding = CaseFolderBinding.objects.filter(case_id=case_id).first()
        if not binding:
            raise ValidationException(message="未绑定文件夹", errors={"case_id": case_id})

        storage_type = getattr(binding, "storage_type", "local")
        if storage_type == "local":
            folder = Path(binding.resolved_folder_path)
            if not folder.exists() or not folder.is_dir():
                # 文件夹不可访问，尝试自动修复合同路径后再检查
                CaseFolderScanService._try_repair_binding_path(binding)
                # 修复后重新检查
                folder = Path(binding.resolved_folder_path)
                if not folder.exists() or not folder.is_dir():
                    raise ValidationException(
                        message="绑定文件夹不可访问", errors={"folder_path": binding.resolved_folder_path}
                    )
        else:
            # Cloud storage: use provider to check accessibility
            from apps.core.cloud_storage.factory import create_provider_for_binding

            provider = create_provider_for_binding(binding)
            try:
                accessible = provider.is_dir(binding.resolved_folder_path) or provider.exists(
                    binding.resolved_folder_path
                )
            except Exception:
                accessible = False
            if not accessible:
                raise ValidationException(
                    message="绑定文件夹不可访问", errors={"folder_path": binding.resolved_folder_path}
                )

        return binding

    @staticmethod
    def _try_repair_binding_path(binding: CaseFolderBinding) -> None:
        """当文件夹不可访问时，尝试自动修复合同路径以恢复可达性。

        案件的 resolved_folder_path 依赖合同路径 + relative_path，
        如果合同路径因改名/移动而失效，通过 inode 搜索可以自动恢复。
        """
        if not binding.relative_path:
            return

        try:
            case = binding.case
        except (AttributeError, TypeError):
            return

        if not case.contract_id:
            return

        try:
            contract = case.contract
        except (AttributeError, TypeError):
            return

        contract_binding = getattr(contract, "folder_binding", None)
        if not contract_binding:
            return

        from apps.core.dependencies import build_contract_folder_binding_service

        contract_binding_service = build_contract_folder_binding_service()
        is_accessible, auto_repaired = contract_binding_service.check_and_repair_path(contract_binding)
        logger.info(
            "case_folder_scan_auto_repair",
            extra={
                "case_id": binding.case_id,
                "binding_id": binding.id,
                "resolved_folder_path": binding.resolved_folder_path,
                "is_accessible": is_accessible,
                "auto_repaired": auto_repaired,
            },
        )

    def _extract_scan_subfolder(self, payload: dict[str, Any] | None) -> str:
        scope = (payload or {}).get("scan_scope") or {}
        return str(scope.get("scan_subfolder") or "").strip()

    def _make_provider_for_binding(self, binding: CaseFolderBinding) -> Any | None:  # pragma: no cover
        """Create a cloud storage provider for the binding, or None for local."""
        storage_type = getattr(binding, "storage_type", "local")
        if storage_type == "local":
            return None
        from apps.core.cloud_storage.factory import create_provider_for_binding

        return create_provider_for_binding(binding)

    def _normalize_candidates_for_scan_scope(
        self,
        candidates: list[dict[str, Any]],
        payload: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        should_force_for_scope = self._should_force_our_party_for_filing_materials(payload)
        normalized: list[dict[str, Any]] = []
        for item in candidates:
            candidate = dict(item or {})
            should_force_for_candidate = self._should_force_our_party_for_candidate(candidate)
            if not should_force_for_scope and not should_force_for_candidate:
                normalized.append(candidate)
                continue
            candidate["suggested_category"] = "party"
            candidate["suggested_side"] = "our"
            if not str(candidate.get("reason") or "").strip():
                candidate["reason"] = self._FORCE_OUR_PARTY_REASON
            normalized.append(candidate)
        return normalized

    def _should_force_our_party_for_filing_materials(self, payload: dict[str, Any] | None) -> bool:
        scope = (payload or {}).get("scan_scope") or {}
        scan_subfolder = str(scope.get("scan_subfolder") or "").strip()
        scan_folder = str(scope.get("scan_folder") or "").strip()
        return self._contains_force_our_party_folder_keyword(
            scan_subfolder
        ) or self._contains_force_our_party_folder_keyword(scan_folder)

    def _should_force_our_party_for_candidate(self, candidate: dict[str, Any] | None) -> bool:
        source_path = str((candidate or {}).get("source_path") or "").strip()
        if not source_path:
            return False
        return self._contains_force_our_party_folder_keyword(source_path)

    @classmethod
    def _contains_force_our_party_folder_keyword(cls, text: str) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            return False
        return any(keyword in normalized for keyword in cls._FORCE_OUR_PARTY_FOLDER_KEYWORDS)

    def _extract_enable_recognition(self, payload: dict[str, Any] | None) -> bool:
        options = (payload or {}).get("scan_options") or {}
        if "enable_recognition" not in options:
            return True
        return bool(options.get("enable_recognition"))

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
                # 当 root="/" 时，任何以 "/" 开头且不等于 "/" 的路径都在范围内
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

    def _build_classification_context(self, case: Case) -> dict[str, Any]:
        our_party_ids: list[int] = []
        opponent_party_ids: list[int] = []
        our_party_names: list[str] = []
        opponent_party_names: list[str] = []

        for party in case.parties.all():
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
        return f"{base}?{urlencode({'scan_session': str(session_id), 'open_scan': '1'})}"


def run_case_folder_scan_task(session_id: str) -> None:  # pragma: no cover
    """Django-Q 任务入口。"""
    CaseFolderScanService().run_scan_task(session_id=session_id)
