"""绑定文件夹扫描服务。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException
from apps.document_recognition.services.text_extraction_service import TextExtractionService

from .material_classification_service import MaterialClassificationService

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, str | None], None]


@dataclass(frozen=True)
class _VersionInfo:
    base_name: str
    version_token: str
    version_rank: int


class BoundFolderScanService:
    """扫描绑定目录中的 PDF，并生成分类建议。"""

    _MAX_TEXT_EXCERPT = 2000
    _SCAN_MAX_PAGES = 3

    _PATTERN_V = re.compile(r"^(?P<base>.*?)[\s._-]*[Vv](?P<num>\d+)$")
    _PATTERN_BRACKET = re.compile(r"^(?P<base>.*?)[\s._-]*[（(](?P<num>\d+)[）)]$")
    _PATTERN_COPY = re.compile(r"^(?P<base>.*?)[\s._-]*(?P<label>副本|复制)$")

    def __init__(
        self,
        *,
        max_candidates: int = 300,
        text_extraction_service: TextExtractionService | None = None,
        classification_service: MaterialClassificationService | None = None,
    ) -> None:
        self._max_candidates = max_candidates
        self._text_extraction_service = text_extraction_service or TextExtractionService(
            text_limit=self._MAX_TEXT_EXCERPT,
            max_pages=self._SCAN_MAX_PAGES,
        )
        self._classification_service = classification_service or MaterialClassificationService()

    def scan_folder(
        self,
        *,
        folder_path: str,
        domain: str,
        progress_callback: ProgressCallback | None = None,
        enable_recognition: bool = True,
        classification_context: dict[str, Any] | None = None,
        scan_subfolder: str = "",
    ) -> dict[str, Any]:
        root = Path(folder_path).expanduser()
        if not root.exists() or not root.is_dir():
            raise ValidationException(
                message=_("绑定文件夹不可访问"),
                code="FOLDER_NOT_ACCESSIBLE",
                errors={"folder_path": str(root)},
            )

        self._notify(progress_callback, "scanning", 5, None)
        all_pdf_files = self._collect_pdf_files(root)
        deduped = self._deduplicate_files(all_pdf_files)

        if len(deduped) > self._max_candidates:
            deduped = deduped[: self._max_candidates]

        candidates: list[dict[str, Any]] = []

        total = len(deduped)
        for idx, item in enumerate(deduped, start=1):
            current_file = item["path"].name
            progress = self._calc_progress(idx=idx, total=total)

            self._notify(progress_callback, "extracting", progress, current_file)
            extraction_method = "none"
            text_excerpt = ""
            if enable_recognition:
                try:
                    extraction = self._text_extraction_service.extract_text(item["path"].as_posix())
                    extraction_method = extraction.extraction_method if extraction.success else "none"
                    text_excerpt = (extraction.text or "")[: self._MAX_TEXT_EXCERPT]
                except Exception:
                    logger.exception("scan_extract_failed", extra={"path": item["path"].as_posix()})

            self._notify(progress_callback, "classifying", progress, current_file)

            # 从文件路径中提取相对于扫描根目录的父文件夹名，作为类型提示
            parent_folder_hint = self._extract_parent_folder_hint(
                file_path=item["path"],
                scan_root=root,
            )

            candidate = self._build_candidate(
                path=item["path"],
                base_name=item["base_name"],
                version_token=item["version_token"],
                extraction_method=extraction_method,
                text_excerpt=text_excerpt,
                domain=domain,
                enable_recognition=enable_recognition,
                classification_context=classification_context,
                scan_subfolder=scan_subfolder,
                parent_folder_hint=parent_folder_hint,
            )
            candidates.append(candidate)

        self._notify(progress_callback, "completed", 100, None)

        return {
            "summary": {
                "total_files": len(all_pdf_files),
                "deduped_files": len(deduped),
                "classified_files": len(candidates),
            },
            "candidates": candidates,
        }

    def _build_candidate(
        self,
        *,
        path: Path,
        base_name: str,
        version_token: str,
        extraction_method: str,
        text_excerpt: str,
        domain: str,
        enable_recognition: bool,
        classification_context: dict[str, Any] | None,
        scan_subfolder: str = "",
        parent_folder_hint: str = "",
    ) -> dict[str, Any]:
        stat = path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
        candidate: dict[str, Any] = {
            "source_path": path.as_posix(),
            "filename": path.name,
            "file_size": int(stat.st_size),
            "modified_at": modified_at,
            "base_name": base_name,
            "version_token": version_token,
            "extract_method": extraction_method,
            "text_excerpt": text_excerpt,
            "selected": True,
        }

        if domain == "contract":
            suggestion = self._classification_service.classify_contract_material(
                filename=path.name,
                text_excerpt=text_excerpt,
                enable_ai=enable_recognition,
            )
            candidate.update(
                {
                    "suggested_category": suggestion.get("category", "invoice"),
                    "confidence": float(suggestion.get("confidence", 0.0) or 0.0),
                    "reason": str(suggestion.get("reason") or ""),
                }
            )
            return candidate

        if domain == "case":
            suggestion = self._classification_service.classify_case_material(
                filename=path.name,
                text_excerpt=text_excerpt,
                source_path=path.as_posix(),
                enable_ai=enable_recognition,
                context=classification_context,
                scan_subfolder=scan_subfolder,
                parent_folder_hint=parent_folder_hint,
            )
            candidate.update(
                {
                    "suggested_category": suggestion.get("category", "unknown"),
                    "suggested_side": suggestion.get("side", "unknown"),
                    "type_name_hint": suggestion.get("type_name_hint", ""),
                    "suggested_supervising_authority_id": suggestion.get("suggested_supervising_authority_id"),
                    "suggested_party_ids": suggestion.get("suggested_party_ids", []),
                    "confidence": float(suggestion.get("confidence", 0.0) or 0.0),
                    "reason": str(suggestion.get("reason") or ""),
                }
            )
            return candidate

        raise ValidationException(
            message=_("不支持的扫描领域"), code="UNSUPPORTED_SCAN_DOMAIN", errors={"domain": domain}
        )

    @staticmethod
    def _extract_parent_folder_hint(file_path: Path, scan_root: Path) -> str:
        """从文件路径中提取相对于扫描根目录的直接父文件夹名，作为类型提示。

        例如扫描根目录为 "2-立案材料"，文件位于 "2-立案材料/执行申请书/xxx.pdf"，
        则返回 "执行申请书"；若文件直接在根目录下，则返回 ""。
        """
        try:
            relative = file_path.parent.relative_to(scan_root)
        except ValueError:
            return ""
        # 如果文件直接在扫描根目录下（relative 是 "."），无父文件夹提示
        if str(relative) == ".":
            return ""
        # 取最靠近文件的父目录名（relative 可能是 "执行申请书" 或 "子目录A/子目录B"）
        # 对于多级，取第一级（用户命名的分组目录）
        first_part = Path(relative).parts[0] if Path(relative).parts else ""
        # 去掉编号前缀：2-立案材料 → 立案材料
        return re.sub(r"^[\d]+[\s.\-_]*[\)）]?\s*", "", first_part).strip() or first_part

    @staticmethod
    def _notify(callback: ProgressCallback | None, status: str, progress: int, current_file: str | None) -> None:
        if callback is None:
            return
        callback(status, progress, current_file)

    @staticmethod
    def _calc_progress(*, idx: int, total: int) -> int:
        if total <= 0:
            return 100
        return min(99, max(10, int((idx / total) * 90) + 9))

    @staticmethod
    def _collect_pdf_files(root: Path) -> list[Path]:
        files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"]
        files.sort(key=lambda x: x.as_posix())
        return files

    def _deduplicate_files(self, files: list[Path]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for file_path in files:
            stem = file_path.stem
            version = self._parse_version(stem)
            group_key = self._normalize_group_key(version.base_name)
            grouped.setdefault(group_key, []).append(
                {
                    "path": file_path,
                    "base_name": version.base_name,
                    "version_token": version.version_token,
                    "version_rank": version.version_rank,
                    "mtime": file_path.stat().st_mtime,
                }
            )

        deduped: list[dict[str, Any]] = []
        for group_items in grouped.values():
            group_items.sort(key=lambda x: (-x["version_rank"], -x["mtime"], x["path"].as_posix()))
            deduped.append(group_items[0])

        deduped.sort(key=lambda x: x["path"].as_posix())
        return deduped

    def _parse_version(self, stem: str) -> _VersionInfo:
        candidate = stem.strip()

        match_v = self._PATTERN_V.match(candidate)
        if match_v:
            num = int(match_v.group("num"))
            base_name = self._clean_base_name(match_v.group("base"))
            return _VersionInfo(base_name=base_name, version_token=f"V{num}", version_rank=100 + num)

        match_bracket = self._PATTERN_BRACKET.match(candidate)
        if match_bracket:
            num = int(match_bracket.group("num"))
            base_name = self._clean_base_name(match_bracket.group("base"))
            return _VersionInfo(base_name=base_name, version_token=f"({num})", version_rank=100 + num)

        match_copy = self._PATTERN_COPY.match(candidate)
        if match_copy:
            base_name = self._clean_base_name(match_copy.group("base"))
            return _VersionInfo(base_name=base_name, version_token=str(match_copy.group("label")), version_rank=0)

        return _VersionInfo(base_name=self._clean_base_name(candidate), version_token="", version_rank=1)

    @staticmethod
    def _clean_base_name(base_name: str) -> str:
        value = (base_name or "").strip()
        value = re.sub(r"[\s._-]+", " ", value)
        return value.strip() or (base_name or "").strip()

    @staticmethod
    def _normalize_group_key(base_name: str) -> str:
        normalized = re.sub(r"[\s._-]+", " ", (base_name or "").strip().lower())
        return normalized or "_"
