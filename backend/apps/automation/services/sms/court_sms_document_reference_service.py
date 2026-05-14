"""法院短信文书引用解析服务。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from apps.automation.models import CourtSMS
from apps.cases.services.log.case_log_attachment_storage_service import CaseLogAttachmentStorageService


@dataclass(frozen=True)
class CourtSMSDocumentReference:
    """法院短信文书引用信息。"""

    display_name: str
    file_path: str
    source: str
    court_document_id: int | None = None
    download_status_display: str | None = None
    original_name: str = ""
    archived_subdir: str = ""
    recommended_subdir: str = ""
    recommendation_reason: str = ""


class CourtSMSDocumentReferenceService:
    """聚合 CourtSMS 文书引用（多来源 + 去重）。"""

    def collect(self, sms: CourtSMS) -> list[CourtSMSDocumentReference]:
        refs: list[CourtSMSDocumentReference] = []
        seen_paths: set[str] = set()
        seen_names: set[str] = set()
        storage_service = CaseLogAttachmentStorageService()

        self._collect_from_court_documents(sms, refs, seen_paths, seen_names)
        self._collect_from_sms_paths(sms, refs, seen_paths, seen_names)
        self._collect_from_task_result(sms, refs, seen_paths, seen_names)
        self._collect_from_case_log_attachments(sms, refs, seen_paths, seen_names, storage_service)
        self._enrich_with_archive_diagnostics(sms, refs, storage_service)

        return refs

    def _collect_from_court_documents(
        self, sms: CourtSMS, refs: list[CourtSMSDocumentReference], seen_paths: set[str], seen_names: set[str]
    ) -> None:
        if not sms.scraper_task or not hasattr(sms.scraper_task, "documents"):
            return

        for doc in sms.scraper_task.documents.filter(download_status="success"):
            normalized = self._normalize_existing_path(doc.local_file_path)
            if not normalized or normalized in seen_paths:
                continue
            file_name = Path(normalized).name
            if file_name in seen_names:
                continue
            seen_paths.add(normalized)
            seen_names.add(file_name)
            refs.append(
                CourtSMSDocumentReference(
                    display_name=Path(normalized).name,
                    file_path=normalized,
                    source="court_document",
                    court_document_id=int(doc.id),
                    download_status_display=doc.get_download_status_display(),
                    original_name=self._build_original_document_name(doc),
                )
            )

    def _collect_from_sms_paths(
        self, sms: CourtSMS, refs: list[CourtSMSDocumentReference], seen_paths: set[str], seen_names: set[str]
    ) -> None:
        paths = sms.document_file_paths if isinstance(sms.document_file_paths, list) else []
        for raw_path in paths:
            normalized = self._normalize_existing_path(raw_path)
            if not normalized or normalized in seen_paths:
                continue
            file_name = Path(normalized).name
            if file_name in seen_names:
                continue
            seen_paths.add(normalized)
            seen_names.add(file_name)
            refs.append(
                CourtSMSDocumentReference(
                    display_name=Path(normalized).name,
                    file_path=normalized,
                    source="sms_reference",
                )
            )

    def _collect_from_task_result(
        self, sms: CourtSMS, refs: list[CourtSMSDocumentReference], seen_paths: set[str], seen_names: set[str]
    ) -> None:
        if not sms.scraper_task or not isinstance(sms.scraper_task.result, dict):
            return

        result = sms.scraper_task.result
        candidate_paths = [*result.get("renamed_files", []), *result.get("files", [])]
        for raw_path in candidate_paths:
            normalized = self._normalize_existing_path(raw_path)
            if not normalized or normalized in seen_paths:
                continue
            file_name = Path(normalized).name
            if file_name in seen_names:
                continue
            seen_paths.add(normalized)
            seen_names.add(file_name)
            refs.append(
                CourtSMSDocumentReference(
                    display_name=Path(normalized).name,
                    file_path=normalized,
                    source="task_result",
                )
            )

    def _collect_from_case_log_attachments(
        self,
        sms: CourtSMS,
        refs: list[CourtSMSDocumentReference],
        seen_paths: set[str],
        seen_names: set[str],
        storage_service: CaseLogAttachmentStorageService,
    ) -> None:
        if not sms.case_log:
            return

        attachments = getattr(sms.case_log, "attachments", None)
        if attachments is None:
            return

        for attachment in attachments.all():
            normalized = self._resolve_case_log_attachment_path(attachment, storage_service)
            display_names = self._get_case_log_attachment_display_names(attachment)
            if not normalized or normalized in seen_paths:
                continue
            file_name = Path(normalized).name
            if file_name in seen_names or any(name in seen_names for name in display_names):
                continue
            seen_paths.add(normalized)
            seen_names.add(file_name)
            seen_names.update(display_names)
            refs.append(
                CourtSMSDocumentReference(
                    display_name=Path(normalized).name,
                    file_path=normalized,
                    source="case_log_attachment",
                    original_name=str(getattr(attachment, "original_filename", "") or ""),
                    archived_subdir=str(getattr(attachment, "subdir_path", "") or ""),
                )
            )

    def merge_and_save_paths(self, sms: CourtSMS, paths: list[str]) -> None:
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

    def _normalize_existing_path(self, raw_path: str | None) -> str | None:
        if not raw_path:
            return None

        path = Path(str(raw_path))
        if not path.is_absolute():
            path = Path(settings.MEDIA_ROOT) / path

        if not path.exists():
            return None

        return str(path.resolve())

    def _build_original_document_name(self, doc: object) -> str:
        raw_name = str(getattr(doc, "c_wsmc", "") or "").strip()
        file_ext = str(getattr(doc, "c_wjgs", "") or "").strip().lstrip(".")
        if not raw_name:
            return ""
        return raw_name if not file_ext else f"{raw_name}.{file_ext}"

    def _enrich_with_archive_diagnostics(
        self,
        sms: CourtSMS,
        refs: list[CourtSMSDocumentReference],
        storage_service: CaseLogAttachmentStorageService,
    ) -> None:
        if not refs or not getattr(sms, "case_id", None):
            return

        attachment_by_abs_path: dict[str, object] = {}
        attachment_by_display_name: dict[str, list[object]] = {}
        if getattr(sms, "case_log", None):
            attachments = getattr(sms.case_log, "attachments", None)
            if attachments is not None:
                for attachment in attachments.all():
                    normalized = self._resolve_case_log_attachment_path(attachment, storage_service)
                    if normalized:
                        attachment_by_abs_path[normalized] = attachment
                    for display_name in self._get_case_log_attachment_display_names(attachment):
                        attachment_by_display_name.setdefault(display_name, []).append(attachment)

        saved_recommendation_names_by_path: dict[str, str] = {}
        scraper_task = getattr(sms, "scraper_task", None)
        result = getattr(scraper_task, "result", None)
        if isinstance(result, dict):
            raw_mapping = result.get("recommendation_names_by_path")
            if isinstance(raw_mapping, dict):
                for raw_path, raw_name in raw_mapping.items():
                    normalized_path = self._normalize_existing_path(str(raw_path or ""))
                    recommendation_name = str(raw_name or "").strip()
                    if normalized_path and recommendation_name:
                        saved_recommendation_names_by_path[normalized_path] = recommendation_name

        for index, ref in enumerate(refs):
            attachment = attachment_by_abs_path.get(ref.file_path)
            if attachment is None:
                attachment = self._match_attachment_by_display_name(
                    attachment_by_display_name,
                    ref.display_name,
                    ref.original_name,
                )
            archived_subdir = ref.archived_subdir
            original_name = saved_recommendation_names_by_path.get(ref.file_path, "") or ref.original_name
            if attachment is not None:
                if not archived_subdir:
                    archived_subdir = str(getattr(attachment, "subdir_path", "") or "")
                if not original_name:
                    original_name = str(getattr(attachment, "original_filename", "") or "")

            recommendation_name = original_name or ref.display_name
            recommendation = storage_service.recommend_attachment_subdir(
                case_id=int(sms.case_id),
                log=getattr(sms, "case_log", None),
                file_name=ref.display_name,
                source_scene="court_sms_attachment",
                recommendation_file_name=recommendation_name,
            )
            refs[index] = CourtSMSDocumentReference(
                display_name=ref.display_name,
                file_path=ref.file_path,
                source=ref.source,
                court_document_id=ref.court_document_id,
                download_status_display=ref.download_status_display,
                original_name=original_name,
                archived_subdir=archived_subdir,
                recommended_subdir=str(recommendation.get("recommended_subdir") or ""),
                recommendation_reason=str(recommendation.get("reason") or ""),
            )

    def _resolve_case_log_attachment_path(
        self,
        attachment: object,
        storage_service: CaseLogAttachmentStorageService,
    ) -> str | None:
        try:
            resolved = storage_service.resolve_attachment(attachment)
        except Exception:
            resolved = None
        if resolved is not None and getattr(resolved, "exists", False) and getattr(resolved, "abs_path", ""):
            return str(Path(str(resolved.abs_path)).expanduser().resolve())

        file_obj = getattr(attachment, "file", None)
        raw_path = getattr(file_obj, "path", "") or getattr(file_obj, "name", "")
        return self._normalize_existing_path(raw_path)

    def _get_case_log_attachment_display_names(self, attachment: object) -> list[str]:
        candidates: list[str] = []

        original_name = str(getattr(attachment, "original_filename", "") or "").strip()
        if original_name:
            candidates.append(original_name)

        relative_file_path = str(getattr(attachment, "relative_file_path", "") or "").strip()
        if relative_file_path:
            candidates.append(Path(relative_file_path).name)

        file_name = str(getattr(getattr(attachment, "file", None), "name", "") or "").strip()
        if file_name:
            candidates.append(Path(file_name).name)

        unique_candidates: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate and candidate not in seen:
                unique_candidates.append(candidate)
                seen.add(candidate)
        return unique_candidates

    def _match_attachment_by_display_name(
        self,
        attachment_by_display_name: dict[str, list[object]],
        *names: str,
    ) -> object | None:
        for name in names:
            normalized_name = str(name or "").strip()
            if not normalized_name:
                continue
            matches = attachment_by_display_name.get(normalized_name, [])
            if len(matches) == 1:
                return matches[0]
        return None
