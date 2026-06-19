"""候选文件后处理：归档匹配、docx 收集、已导入标记。"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from apps.contracts.models import FinalizedMaterial
from apps.contracts.services.archive.category_mapping import get_archive_category
from apps.contracts.services.contract.integrations.archive_classifier import classify_archive_material

from .file_hash_utils import compute_file_hash, compute_file_hash_from_bytes

logger = logging.getLogger(__name__)


def _normalize_docx_name(filename: str) -> str:
    """标准化文件名用于关键词匹配。"""
    return re.sub(r"\s+", "", str(filename or "").strip().lower())


class CandidatePostProcessor:
    """候选文件后处理器：归档清单匹配、docx 收集、已导入标记。"""

    def __init__(self, scan_service: Any) -> None:
        self._scan_service = scan_service

    def _relative_path_str(self, *, source_path: str, scan_root: Path) -> str:
        """计算文件父目录相对扫描根目录的路径，失败返回空字符串。"""
        try:
            file_path = Path(source_path).expanduser().resolve()
            parent_rel = file_path.parent.relative_to(scan_root)
            if str(parent_rel) == ".":
                return ""
            return parent_rel.as_posix()
        except (ValueError, RuntimeError):
            return ""

    def post_process_candidates(
        self,
        *,
        candidates: list[dict[str, Any]],
        archive_category: str,
        scan_folder: str,
        contract_id: int = 0,
        storage_provider: Any | None = None,
    ) -> list[dict[str, Any]]:
        """扫描后处理：归档清单项匹配 + docx 文件收集 + 跳过项过滤。"""
        processed: list[dict[str, Any]] = []
        if storage_provider is not None:
            scan_root_posix: PurePosixPath | None = PurePosixPath(scan_folder)
        else:
            scan_root_posix = None
            scan_root = Path(scan_folder).expanduser().resolve()

        for candidate in candidates:
            suggested_category = str(candidate.get("suggested_category") or "")

            if suggested_category == "archive_document":
                result = classify_archive_material(
                    filename=str(candidate.get("filename") or ""),
                    source_path=str(candidate.get("source_path") or ""),
                    archive_category=archive_category,
                )

                if result["category"] == "skip":
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
                    candidate["suggested_category"] = "case_material"
                    candidate["archive_item_code"] = ""
                    candidate["archive_item_name"] = "未匹配"
                    candidate["reason"] = result["reason"]
                    candidate["selected"] = False

            elif suggested_category == "authorization_material":
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

            filename_lower = str(candidate.get("filename") or "").lower()
            if any(kw in filename_lower for kw in ("保单", "保函")):
                candidate["selected"] = False

            if candidate.get("suggested_category") == "case_material":
                if storage_provider is not None:
                    source = str(candidate.get("source_path") or "")
                    try:
                        assert scan_root_posix is not None
                        rel_path = str(PurePosixPath(source).relative_to(scan_root_posix))
                    except ValueError:
                        rel_path = source
                else:
                    rel_path = self._relative_path_str(
                        source_path=str(candidate.get("source_path") or ""),
                        scan_root=scan_root,
                    )
                if rel_path:
                    candidate["reason"] = rel_path

            processed.append(candidate)

        if archive_category == "non_litigation":
            docx_candidates = self._collect_docx_files(scan_folder, archive_category, storage_provider=storage_provider)
            processed.extend(docx_candidates)

        if contract_id:
            self._mark_already_imported(processed, contract_id=contract_id, storage_provider=storage_provider)

        return processed

    def _collect_docx_files(
        self,
        scan_folder: str,
        archive_category: str,
        storage_provider: Any | None = None,
    ) -> list[dict[str, Any]]:
        """单独收集 docx/doc 文件，仅非诉项目且仅含修订版/批注版关键词。"""
        if archive_category != "non_litigation":
            return []

        _DOCX_REVISION_KEYWORDS = ("修订版", "批注版", "律师修订")

        if storage_provider is not None:
            return self._collect_docx_files_cloud(scan_folder, storage_provider, _DOCX_REVISION_KEYWORDS)

        root = Path(scan_folder).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return []

        docx_files = [
            p
            for p in root.rglob("*")
            if p.is_file()
            and p.suffix.lower() in (".docx", ".doc")
            and any(kw in _normalize_docx_name(p.name) for kw in _DOCX_REVISION_KEYWORDS)
        ]
        docx_files.sort(key=lambda x: x.as_posix())

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

            candidates.append(
                {
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
                }
            )

        return candidates

    def _collect_docx_files_cloud(
        self,
        scan_folder: str,
        storage_provider: Any,
        revision_keywords: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        """云存储版本的 docx 文件收集。"""
        all_files: list[dict[str, Any]] = []
        for _dirpath, _subdirs, files in storage_provider.walk(scan_folder):
            for f in files:
                if not f.is_dir and PurePosixPath(f.name).suffix.lower() in (".docx", ".doc"):
                    if any(kw in _normalize_docx_name(f.name) for kw in revision_keywords):
                        all_files.append(
                            {
                                "name": f.name,
                                "path": f.path,
                                "size": f.size,
                                "modified_at": f.modified_at,
                            }
                        )

        if not all_files:
            return []

        all_files.sort(key=lambda x: x["path"])

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in all_files:
            stem = PurePosixPath(item["name"]).stem
            grouped[stem].append(item)

        deduped: list[dict[str, Any]] = []
        for group_items in grouped.values():
            group_items.sort(key=lambda x: (-x["modified_at"], x["path"]))
            deduped.append(group_items[0])

        candidates: list[dict[str, Any]] = []
        for item in deduped:
            archive_item_code = ""
            archive_item_name = "未匹配"
            reason = "常法docx（修订版/批注版）→ 转 PDF"
            normalized_name = _normalize_docx_name(item["name"])

            if "律师函" in normalized_name:
                archive_item_code = "nl_8"
                archive_item_name = "法律意见书、律师函等"
                reason = "常法docx（律师函）→ nl_8"
            else:
                archive_item_code = "nl_9"
                archive_item_name = "案件其它关联材料"
                reason = "常法docx（修订版/批注版）→ nl_9"

            candidates.append(
                {
                    "source_path": item["path"],
                    "filename": item["name"],
                    "file_size": item["size"],
                    "modified_at": "",
                    "base_name": normalized_name,
                    "version_token": "",
                    "extract_method": "none",
                    "text_excerpt": "",
                    "suggested_category": "case_material",
                    "confidence": 0.85,
                    "reason": reason,
                    "selected": True,
                    "is_docx": True,
                    "archive_item_code": archive_item_code,
                    "archive_item_name": archive_item_name,
                }
            )

        return candidates

    def _mark_already_imported(
        self,
        candidates: list[dict[str, Any]],
        *,
        contract_id: int,
        storage_provider: Any | None = None,
    ) -> None:
        """标记已导入文件：计算文件哈希，与已有材料比对。"""
        existing_hashes: set[str] = set(
            FinalizedMaterial.objects.filter(
                contract_id=contract_id,
                content_hash__gt="",
            ).values_list("content_hash", flat=True)
        )

        if not existing_hashes:
            for candidate in candidates:
                candidate["already_imported"] = False
            return

        for candidate in candidates:
            if candidate.get("skip_reason"):
                candidate["already_imported"] = False
                continue

            source_path = str(candidate.get("source_path") or "").strip()
            if not source_path:
                continue

            try:
                if storage_provider is not None:
                    file_bytes = storage_provider.read_file(source_path)
                    content_hash = compute_file_hash_from_bytes(file_bytes)
                else:
                    file_path = Path(source_path)
                    if not file_path.exists() or not file_path.is_file():
                        continue
                    content_hash = compute_file_hash(file_path)
            except Exception:
                logger.warning("mark_imported_hash_failed", extra={"source_path": source_path})
                continue

            if content_hash and content_hash in existing_hashes:
                candidate["already_imported"] = True
                candidate["selected"] = False
            else:
                candidate["already_imported"] = False
