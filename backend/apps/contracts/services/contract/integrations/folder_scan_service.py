"""合同文件夹自动捕获服务。"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import fitz
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
from apps.contracts.services.archive.category_mapping import get_archive_category
from apps.contracts.services.contract.integrations.archive_classifier import (
    classify_archive_material,
    collect_archive_item_options,
    collect_work_log_suggestions,
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
    _QUALITY_CARD_KEYWORD = "律师办案服务质量监督卡"
    _QUALITY_CARD_TITLE = "合同正本与律师办案服务质量监督卡"

    def __init__(self, *, scan_service: BoundFolderScanService | None = None) -> None:
        self._scan_service = scan_service or BoundFolderScanService()
        self._material_service = MaterialService()

    def start_scan(
        self,
        *,
        contract_id: int,
        started_by: Any | None,
        rescan: bool = False,
        scan_subfolder: str = "",
    ) -> ContractFolderScanSession:
        self._ensure_contract_exists(contract_id)
        binding = self._get_accessible_binding(contract_id)
        scan_scope = self._resolve_scan_scope(binding.folder_path, scan_subfolder)

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
                    message=_("已有进行中的扫描任务，请等待完成或使用\u201c重新扫描\u201d"),
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

    def list_scan_subfolders(self, *, contract_id: int) -> dict[str, Any]:
        self._ensure_contract_exists(contract_id)
        binding = self._get_accessible_binding(contract_id)
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

    def get_session(self, *, contract_id: int, session_id: UUID) -> ContractFolderScanSession:
        try:
            return ContractFolderScanSession.objects.get(id=session_id, contract_id=contract_id)
        except ContractFolderScanSession.DoesNotExist:
            raise NotFoundError(_("扫描会话不存在")) from None

    def get_latest_session(self, *, contract_id: int) -> ContractFolderScanSession | None:
        """返回合同最新的扫描会话，没有则返回 None。"""
        return (
            ContractFolderScanSession.objects.filter(contract_id=contract_id)
            .order_by("-created_at")
            .first()
        )

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
    ) -> dict[str, Any]:
        session = self.get_session(contract_id=contract_id, session_id=session_id)
        if session.status == ContractFolderScanStatus.IMPORTED:
            raise ValidationException(message=_("该扫描已导入，请重新扫描"), errors={"status": session.status})
        if session.status != ContractFolderScanStatus.COMPLETED:
            raise ValidationException(message=_("扫描尚未完成"), errors={"status": session.status})

        payload = dict(session.result_payload or {})
        candidates = payload.get("candidates") or []
        candidate_map = {str(item.get("source_path") or ""): item for item in candidates}

        imported_count = 0
        skipped_dupes = 0
        for item in items:
            if not bool(item.get("selected", True)):
                continue

            source_path = str(item.get("source_path") or "").strip()
            if not source_path or source_path not in candidate_map:
                raise ValidationException(message=_("候选文件不存在"), errors={"source_path": source_path})

            category = str(item.get("category") or "archive_document").strip()
            if category not in {
                MaterialCategory.CONTRACT_ORIGINAL,
                MaterialCategory.SUPPLEMENTARY_AGREEMENT,
                MaterialCategory.INVOICE,
                MaterialCategory.SUPERVISION_CARD,
                MaterialCategory.CASE_MATERIAL,
            }:
                # archive_document / authorization_material 归入案件材料
                category = MaterialCategory.CASE_MATERIAL

            is_docx = bool(item.get("is_docx", False))
            archive_item_code = str(item.get("archive_item_code") or "").strip()

            file_path = Path(source_path)
            if not file_path.exists() or not file_path.is_file():
                raise ValidationException(message=_("源文件不存在"), errors={"source_path": source_path})

            # docx → PDF 转换
            actual_file_path = file_path
            temp_pdf_path: Path | None = None
            if is_docx:
                temp_pdf_path = self._convert_docx_to_temp_pdf(file_path)
                if temp_pdf_path is None:
                    logger.warning("docx_convert_failed_skip", extra={"source_path": source_path})
                    continue
                actual_file_path = temp_pdf_path

            try:
                upload = SimpleUploadedFile(
                    name=actual_file_path.name,
                    content=actual_file_path.read_bytes(),
                    content_type="application/pdf",
                )
                rel_path, original_name = self._material_service.save_material_file(upload, contract_id)
                display_name = original_name
                # 如果原始文件是 docx，显示名保留原 docx 文件名
                if is_docx:
                    display_name = file_path.name

                if category == MaterialCategory.CONTRACT_ORIGINAL and not is_docx and self._has_quality_card_on_last_page(file_path):
                    display_name = self._QUALITY_CARD_TITLE

                material_kwargs: dict[str, Any] = {
                    "contract_id": contract_id,
                    "file_path": rel_path,
                    "original_filename": display_name,
                    "category": category,
                }
                if archive_item_code:
                    material_kwargs["archive_item_code"] = archive_item_code

                # 去重：同一合同下相同文件名+分类的材料不重复创建
                if FinalizedMaterial.objects.filter(
                    contract_id=contract_id,
                    original_filename=display_name,
                    category=category,
                ).exists():
                    skipped_dupes += 1
                    logger.info(
                        "material_duplicate_skipped",
                        extra={"contract_id": contract_id, "filename": display_name, "category": category},
                    )
                    continue

                FinalizedMaterial.objects.create(**material_kwargs)
                imported_count += 1
            finally:
                # 清理临时 PDF 文件
                if temp_pdf_path and temp_pdf_path.exists():
                    temp_pdf_path.unlink(missing_ok=True)

        # 保存确认的工作日志建议
        confirmed_logs = work_log_suggestions or []
        payload["import_result"] = {
            "imported_count": imported_count,
            "skipped_dupes": skipped_dupes,
            "imported_at": timezone.now().isoformat(),
        }
        payload["confirmed_work_log_suggestions"] = confirmed_logs

        # 将工作日志建议写入 CaseLog 模型，使模板可读取
        work_log_imported = self._import_work_log_suggestions(
            contract_id=contract_id,
            confirmed_logs=confirmed_logs,
            actor_id=(session.started_by_id if session.started_by_id else None),
        )
        payload["import_result"]["work_log_imported"] = work_log_imported

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
            "work_log_imported": work_log_imported,
        }

    def run_scan_task(self, *, session_id: str) -> None:
        session = ContractFolderScanSession.objects.select_related("contract").filter(id=session_id).first()
        if not session:
            logger.warning("contract_folder_scan_session_missing", extra={"session_id": session_id})
            return

        try:
            binding = self._get_accessible_binding(session.contract_id)
            payload = dict(session.result_payload or {})
            scan_scope = self._resolve_scan_scope(
                binding.folder_path,
                self._extract_scan_subfolder(payload),
            )

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
                folder_path=scan_scope["scan_folder"],
                domain="contract",
                progress_callback=_progress,
            )
            result["scan_scope"] = scan_scope

            # ── 后处理：归档清单项匹配 + docx 收集 + 工作日志建议 ──
            contract = session.contract
            archive_category = get_archive_category(getattr(contract, "case_type", ""))

            candidates = result.get("candidates") or []
            candidates = self._post_process_candidates(
                candidates=candidates,
                archive_category=archive_category,
                scan_folder=scan_scope["scan_folder"],
            )
            result["candidates"] = candidates

            # 工作日志建议
            work_log_suggestions = collect_work_log_suggestions(
                scan_scope["scan_folder"], archive_category
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
            logger.exception("contract_folder_scan_failed", extra={"session_id": session_id})
            ContractFolderScanSession.objects.filter(id=session.id).update(
                status=ContractFolderScanStatus.FAILED,
                error_message=str(exc),
                updated_at=timezone.now(),
            )

    def _import_work_log_suggestions(
        self,
        *,
        contract_id: int,
        confirmed_logs: list[dict[str, str]],
        actor_id: int | None = None,
    ) -> int:
        """将确认的工作日志建议写入 CaseLog 模型，自动跳过已有相同内容的日志。"""
        if not confirmed_logs:
            return 0

        from apps.core.interfaces import ServiceLocator

        case_service = ServiceLocator.get_case_service()
        cases_dto = case_service.get_cases_by_contract(contract_id)
        if not cases_dto:
            logger.warning("work_log_import_no_case", extra={"contract_id": contract_id})
            return 0

        # 取合同的第一个案件写入日志
        case_id = int(cases_dto[0].id)

        # 获取案件已有日志内容集合，用于去重
        from apps.cases.models import CaseLog

        existing_contents: set[str] = set(
            CaseLog.objects.filter(case_id=case_id).values_list("content", flat=True)
        )

        imported = 0
        for suggestion in confirmed_logs:
            content = str(suggestion.get("content") or "").strip()
            if not content:
                continue
            if content in existing_contents:
                logger.info("work_log_duplicate_skipped", extra={"case_id": case_id, "content": content})
                continue
            try:
                case_service.create_case_log_internal(
                    case_id=case_id,
                    content=content,
                    user_id=actor_id,
                )
                existing_contents.add(content)
                imported += 1
            except Exception:
                logger.exception(
                    "work_log_import_item_failed",
                    extra={"case_id": case_id, "content": content},
                )

        logger.info(
            "work_log_imported",
            extra={"contract_id": contract_id, "case_id": case_id, "count": imported},
        )
        return imported

    def _ensure_contract_exists(self, contract_id: int) -> None:
        if Contract.objects.filter(id=contract_id).exists():
            return
        raise NotFoundError(_("合同不存在"))

    def _get_accessible_binding(self, contract_id: int) -> ContractFolderBinding:
        binding = ContractFolderBinding.objects.filter(contract_id=contract_id).first()
        if not binding:
            raise ValidationException(message=_("未绑定文件夹"), errors={"contract_id": contract_id})

        folder = Path(binding.folder_path)
        if not folder.exists() or not folder.is_dir():
            raise ValidationException(message=_("绑定文件夹不可访问"), errors={"folder_path": binding.folder_path})

        return binding

    def _extract_scan_subfolder(self, payload: dict[str, Any] | None) -> str:
        scope = (payload or {}).get("scan_scope") or {}
        return str(scope.get("scan_subfolder") or "").strip()

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

    @staticmethod
    def _relative_path_str(*, source_path: str, scan_root: Path) -> str:
        """计算文件父目录相对扫描根目录的路径，失败返回空字符串。"""
        try:
            file_path = Path(source_path).expanduser().resolve()
            parent_rel = file_path.parent.relative_to(scan_root)
            # 文件直接在根目录下时返回空
            if str(parent_rel) == ".":
                return ""
            return parent_rel.as_posix()
        except (ValueError, RuntimeError):
            return ""

    def _post_process_candidates(
        self,
        *,
        candidates: list[dict[str, Any]],
        archive_category: str,
        scan_folder: str,
    ) -> list[dict[str, Any]]:
        """扫描后处理：归档清单项匹配 + docx 文件收集 + 跳过项过滤。"""
        processed: list[dict[str, Any]] = []
        scan_root = Path(scan_folder).expanduser().resolve()

        for candidate in candidates:
            suggested_category = str(candidate.get("suggested_category") or "")

            if suggested_category == "archive_document":
                # 对被分类为"归档文书"的文件，尝试匹配归档清单项
                result = classify_archive_material(
                    filename=str(candidate.get("filename") or ""),
                    source_path=str(candidate.get("source_path") or ""),
                    archive_category=archive_category,
                )

                if result["category"] == "skip":
                    # 跳过规则命中，不导入
                    candidate["selected"] = False
                    candidate["skip_reason"] = result.get("reason", "跳过")
                    processed.append(candidate)
                    continue

                if result["archive_item_code"]:
                    candidate["suggested_category"] = "case_material"
                    candidate["archive_item_code"] = result["archive_item_code"]
                    candidate["archive_item_name"] = result["archive_item_name"]
                    candidate["confidence"] = result["confidence"]
                    candidate["reason"] = result["reason"]
                else:
                    # 未匹配，保留但标记，默认取消勾选
                    candidate["suggested_category"] = "case_material"
                    candidate["archive_item_code"] = ""
                    candidate["archive_item_name"] = "未匹配"
                    candidate["reason"] = result["reason"]
                    candidate["selected"] = False

            elif suggested_category == "authorization_material":
                # 授权委托材料归入案件材料（兼容旧缓存），并尝试匹配归档清单项
                candidate["suggested_category"] = "case_material"
                result = classify_archive_material(
                    filename=str(candidate.get("filename") or ""),
                    source_path=str(candidate.get("source_path") or ""),
                    archive_category=archive_category,
                )
                if result.get("archive_item_code"):
                    candidate["archive_item_code"] = result["archive_item_code"]
                    candidate["archive_item_name"] = result["archive_item_name"]
                    candidate["confidence"] = result["confidence"]
                    candidate["reason"] = result["reason"]
                else:
                    candidate["archive_item_code"] = ""
                    candidate["archive_item_name"] = "未匹配"
                    candidate["selected"] = False

            elif suggested_category == "case_material":
                # 案件材料 — 尝试匹配归档清单项
                result = classify_archive_material(
                    filename=str(candidate.get("filename") or ""),
                    source_path=str(candidate.get("source_path") or ""),
                    archive_category=archive_category,
                )
                if result.get("archive_item_code"):
                    candidate["archive_item_code"] = result["archive_item_code"]
                    candidate["archive_item_name"] = result["archive_item_name"]
                    candidate["confidence"] = result["confidence"]
                    candidate["reason"] = result["reason"]
                else:
                    candidate["archive_item_code"] = ""
                    candidate["archive_item_name"] = "未匹配"
                    candidate["selected"] = False

            # 文件名含"保单"/"保函"的默认不勾选（保险类文件通常不需要归档）
            filename_lower = str(candidate.get("filename") or "").lower()
            if any(kw in filename_lower for kw in ("保单", "保函")):
                candidate["selected"] = False

            # 案件材料的 reason 统一替换为相对路径，方便用户定位文件
            if candidate.get("suggested_category") == "case_material":
                rel_path = self._relative_path_str(
                    source_path=str(candidate.get("source_path") or ""),
                    scan_root=scan_root,
                )
                if rel_path:
                    candidate["reason"] = rel_path

            processed.append(candidate)

        # 仅非诉项目收集 docx 文件（修订版/批注版 → 转 PDF）
        if archive_category == "non_litigation":
            docx_candidates = self._collect_docx_files(scan_folder, archive_category)
            processed.extend(docx_candidates)

        return processed

    def _collect_docx_files(
        self,
        scan_folder: str,
        archive_category: str,
    ) -> list[dict[str, Any]]:
        """单独收集 docx/doc 文件，仅非诉项目且仅含修订版/批注版关键词。

        诉讼/刑事项目不收集 docx，只有非诉常法才需要 docx→PDF 流程。
        """
        if archive_category != "non_litigation":
            return []

        root = Path(scan_folder).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return []

        # 仅收集文件名含"修订版"/"批注版"/"律师修订"关键词的 docx
        _DOCX_REVISION_KEYWORDS = ("修订版", "批注版", "律师修订")

        docx_files = [
            p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in (".docx", ".doc")
            and any(kw in _normalize_docx_name(p.name) for kw in _DOCX_REVISION_KEYWORDS)
        ]
        docx_files.sort(key=lambda x: x.as_posix())

        # 用与 PDF 相同的去重逻辑
        deduped = self._scan_service._deduplicate_files(docx_files)

        candidates: list[dict[str, Any]] = []
        for item in deduped:
            file_path = item["path"]
            stat = file_path.stat()

            archive_item_code = ""
            archive_item_name = "未匹配"
            reason = "常法docx（修订版/批注版）→ 转 PDF"
            normalized_name = _normalize_docx_name(file_path.name)

            if "律师函" in normalized_name:
                archive_item_code = "nl_8"
                archive_item_name = "法律意见书、律师函等"
                reason = "常法docx（律师函）→ nl_8"
            else:
                archive_item_code = "nl_9"
                archive_item_name = "案件其它关联材料"
                reason = "常法docx（修订版/批注版）→ nl_9"

            candidates.append({
                "source_path": file_path.as_posix(),
                "filename": file_path.name,
                "file_size": int(stat.st_size),
                "modified_at": "",
                "base_name": item["base_name"],
                "version_token": item["version_token"],
                "extract_method": "none",
                "text_excerpt": "",
                "suggested_category": "case_material",
                "confidence": 0.85,
                "reason": reason,
                "selected": True,
                "is_docx": True,
                "archive_item_code": archive_item_code,
                "archive_item_name": archive_item_name,
            })

        return candidates

    def _convert_docx_to_temp_pdf(self, file_path: Path) -> Path | None:
        """将 docx 文件转换为临时 PDF 文件。返回临时 PDF 路径，失败返回 None。"""
        try:
            from apps.documents.services.infrastructure.pdf_merge_utils import convert_docx_to_pdf

            pdf_path_str = convert_docx_to_pdf(file_path.as_posix())
            if pdf_path_str:
                return Path(pdf_path_str)
            return None
        except (OSError, RuntimeError):
            logger.exception("docx_to_pdf_conversion_failed", extra={"path": file_path.as_posix()})
            return None

    def _has_quality_card_on_last_page(self, file_path: Path) -> bool:
        keyword = self._normalize_for_match(self._QUALITY_CARD_KEYWORD)
        if not keyword:
            return False

        direct_text = self._extract_last_page_text_direct(file_path)
        if keyword in self._normalize_for_match(direct_text):
            return True

        ocr_text = self._extract_last_page_text_with_ocr(file_path)
        return keyword in self._normalize_for_match(ocr_text)

    def _extract_last_page_text_direct(self, file_path: Path) -> str:
        try:
            with fitz.open(file_path.as_posix()) as doc:
                if doc.page_count <= 0:
                    return ""
                page = doc.load_page(doc.page_count - 1)
                return str(page.get_text() or "")
        except (OSError, RuntimeError):
            logger.exception("contract_quality_card_check_direct_failed", extra={"path": file_path.as_posix()})
            return ""

    def _extract_last_page_text_with_ocr(self, file_path: Path) -> str:
        try:
            from apps.automation.services.document.document_processing import extract_text_from_image_with_rapidocr

            with fitz.open(file_path.as_posix()) as doc:
                if doc.page_count <= 0:
                    return ""
                page = doc.load_page(doc.page_count - 1)
                pix = page.get_pixmap()

                with tempfile.NamedTemporaryFile(prefix="contract_last_page_", suffix=".png", delete=False) as tmp:
                    temp_path = Path(tmp.name)
                try:
                    pix.save(temp_path.as_posix())
                    return str(extract_text_from_image_with_rapidocr(temp_path.as_posix()) or "")
                finally:
                    if temp_path.exists():
                        temp_path.unlink(missing_ok=True)
        except (OSError, RuntimeError):
            logger.exception("contract_quality_card_check_ocr_failed", extra={"path": file_path.as_posix()})
            return ""

    def _normalize_for_match(self, text: str) -> str:
        return re.sub(r"\s+", "", str(text or "")).lower()


def run_contract_folder_scan_task(session_id: str) -> None:
    """Django-Q 任务入口。"""
    ContractFolderScanService().run_scan_task(session_id=session_id)


def _normalize_docx_name(filename: str) -> str:
    """标准化文件名用于关键词匹配。"""
    return re.sub(r"\s+", "", str(filename or "").strip().lower())
