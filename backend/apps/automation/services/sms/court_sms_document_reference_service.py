"""法院短信文书引用解析服务。"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from apps.automation.models import CourtSMS
from apps.core.services.storage_service import resolve_media_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CourtSMSDocumentReference:  # pragma: no cover
    """法院短信文书引用信息。"""

    display_name: str
    file_path: str
    source: str
    court_document_id: int | None = None
    download_status_display: str | None = None


class CourtSMSDocumentReferenceService:  # pragma: no cover
    """聚合 CourtSMS 文书引用（多来源 + 去重）。"""

    def collect(self, sms: CourtSMS) -> list[CourtSMSDocumentReference]:  # pragma: no cover
        refs: list[CourtSMSDocumentReference] = []
        seen_paths: set[str] = set()
        seen_names: set[str] = set()
        seen_digests: set[str] = set()

        self._collect_from_court_documents(sms, refs, seen_paths, seen_names, seen_digests)
        self._collect_from_sms_paths(sms, refs, seen_paths, seen_names, seen_digests)
        self._collect_from_task_result(sms, refs, seen_paths, seen_names, seen_digests)
        self._collect_from_case_log_attachments(sms, refs, seen_paths, seen_names, seen_digests)

        return refs

    def _accept_path(
        self,
        raw_path: str | None,
        seen_paths: set[str],
        seen_names: set[str],
        seen_digests: set[str],
    ) -> str | None:  # pragma: no cover
        """路径规范化后做三重去重（绝对路径 / 文件名 / 内容 SHA-256），通过则登记并返回。

        同一份文书会以多副本存在：下载原件（task_result）+ 归档到案件日志的复制件
        （case_log_attachment，重名时带 _N 后缀），路径与文件名都不同，必须按内容
        哈希判同，否则详情里同一份文书出现两次。
        """
        normalized = self._normalize_existing_path(raw_path)
        if not normalized or normalized in seen_paths:
            return None

        file_name = Path(normalized).name
        if file_name in seen_names:
            return None

        digest = self._file_digest(Path(normalized))
        if digest is not None and digest in seen_digests:
            return None

        seen_paths.add(normalized)
        seen_names.add(file_name)
        if digest is not None:
            seen_digests.add(digest)
        return normalized

    def _file_digest(self, path: Path) -> str | None:  # pragma: no cover
        """文件内容 SHA-256（流式读取）；读不到不阻断收集，返回 None。"""
        try:
            if not path.is_file():
                return None
            digest = hashlib.sha256()
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            logger.debug("计算文件 SHA-256 摘要失败（已忽略）", exc_info=True)
            return None

    def has_any_references(self, sms: CourtSMS) -> bool:  # pragma: no cover
        """快速检查是否有文书引用（不做文件系统 I/O，适用于列表页）。"""
        if sms.document_file_paths:
            return True
        if sms.scraper_task:
            if hasattr(sms.scraper_task, "documents") and sms.scraper_task.documents.exists():
                return True
            result = sms.scraper_task.result
            if isinstance(result, dict) and (result.get("renamed_files") or result.get("files")):
                return True
        if sms.case_log:
            attachments = getattr(sms.case_log, "attachments", None)
            if attachments is not None and attachments.exists():
                return True
        return False

    def _collect_from_court_documents(  # pragma: no cover
        self,
        sms: CourtSMS,
        refs: list[CourtSMSDocumentReference],
        seen_paths: set[str],
        seen_names: set[str],
        seen_digests: set[str],
    ) -> None:
        if not sms.scraper_task or not hasattr(sms.scraper_task, "documents"):
            return

        # 用 .all() 走 prefetch 缓存再在内存过滤；对关联直接 .filter() 会绕过缓存
        # 发新查询（async 调用方会因此抛 SynchronousOnlyOperation）
        for doc in sms.scraper_task.documents.all():
            if doc.download_status != "success":
                continue
            normalized = self._accept_path(doc.local_file_path, seen_paths, seen_names, seen_digests)
            if not normalized:
                continue
            refs.append(
                CourtSMSDocumentReference(
                    display_name=Path(normalized).name,
                    file_path=normalized,
                    source="court_document",
                    court_document_id=int(doc.id),
                    download_status_display=doc.get_download_status_display(),
                )
            )

    def _collect_from_sms_paths(  # pragma: no cover
        self,
        sms: CourtSMS,
        refs: list[CourtSMSDocumentReference],
        seen_paths: set[str],
        seen_names: set[str],
        seen_digests: set[str],
    ) -> None:
        paths = sms.document_file_paths if isinstance(sms.document_file_paths, list) else []
        for raw_path in paths:
            normalized = self._accept_path(raw_path, seen_paths, seen_names, seen_digests)
            if not normalized:
                continue
            refs.append(
                CourtSMSDocumentReference(
                    display_name=Path(normalized).name,
                    file_path=normalized,
                    source="sms_reference",
                )
            )

    def _collect_from_task_result(  # pragma: no cover
        self,
        sms: CourtSMS,
        refs: list[CourtSMSDocumentReference],
        seen_paths: set[str],
        seen_names: set[str],
        seen_digests: set[str],
    ) -> None:
        if not sms.scraper_task or not isinstance(sms.scraper_task.result, dict):
            return

        result = sms.scraper_task.result
        candidate_paths = [*result.get("renamed_files", []), *result.get("files", [])]
        for raw_path in candidate_paths:
            normalized = self._accept_path(raw_path, seen_paths, seen_names, seen_digests)
            if not normalized:
                continue
            refs.append(
                CourtSMSDocumentReference(
                    display_name=Path(normalized).name,
                    file_path=normalized,
                    source="task_result",
                )
            )

    def _collect_from_case_log_attachments(  # pragma: no cover
        self,
        sms: CourtSMS,
        refs: list[CourtSMSDocumentReference],
        seen_paths: set[str],
        seen_names: set[str],
        seen_digests: set[str],
    ) -> None:
        if not sms.case_log:
            return

        attachments = getattr(sms.case_log, "attachments", None)
        if attachments is None:
            return

        for attachment in attachments.all():
            file_obj = getattr(attachment, "file", None)
            if not file_obj:
                continue

            raw_path = getattr(file_obj, "path", "") or getattr(file_obj, "name", "")
            normalized = self._accept_path(raw_path, seen_paths, seen_names, seen_digests)
            if not normalized:
                continue
            refs.append(
                CourtSMSDocumentReference(
                    display_name=Path(normalized).name,
                    file_path=normalized,
                    source="case_log_attachment",
                )
            )

    def merge_and_save_paths(self, sms: CourtSMS, paths: list[str]) -> None:  # pragma: no cover
        """将新路径写入短信统一文书引用字段（去重合并）。"""
        existing = sms.document_file_paths if isinstance(sms.document_file_paths, list) else []
        merged: list[str] = []
        seen: set[str] = set()

        for raw_path in [*existing, *paths]:
            normalized = self._normalize_existing_path(raw_path)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)

        if merged == existing:
            return

        sms.document_file_paths = merged
        sms.save(update_fields=["document_file_paths", "updated_at"])

    def _normalize_existing_path(self, raw_path: str | None) -> str | None:  # pragma: no cover
        if not raw_path:
            return None

        path = resolve_media_path(str(raw_path))

        if path.exists():
            return path.resolve().as_posix()

        # 文件被重命名时，尝试在同目录下匹配
        parent = path.parent
        if not parent.is_dir():
            return None

        suffix = path.suffix.lower()
        same_suffix = [f for f in parent.iterdir() if f.is_file() and f.suffix.lower() == suffix]
        if not same_suffix:
            return None

        # 1) stem 前缀匹配（如 民事调解书.pdf → 民事调解书（xxx）_20260514收.pdf）
        stem = path.stem
        prefix_matches = [f for f in same_suffix if f.stem.startswith(stem)]
        if prefix_matches:
            return max(prefix_matches, key=lambda f: f.stat().st_mtime).resolve().as_posix()

        # 2) 兜底：取同后缀最新的文件（适用于完全重命名的情况）
        return max(same_suffix, key=lambda f: f.stat().st_mtime).resolve().as_posix()
