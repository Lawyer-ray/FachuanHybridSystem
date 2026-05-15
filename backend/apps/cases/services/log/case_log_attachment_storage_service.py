"""案件日志附件统一存储服务。"""

from __future__ import annotations

import logging
from typing import Any

from apps.core.services import BusinessFileStorageService, ResolvedBusinessFile, StoredBusinessFile
from apps.core.services.system_config_service import SystemConfigService

logger = logging.getLogger(__name__)


class CaseLogAttachmentStorageService:
    DEFAULT_SUBDIR = "案件日志附件"

    def __init__(self, business_storage_service: BusinessFileStorageService | None = None) -> None:
        self._business_storage_service = business_storage_service or BusinessFileStorageService()

    def recommend_attachment_subdir(
        self,
        *,
        case_id: int,
        log: Any | None = None,
        source_subfolder: str = "",
        file_name: str = "",
        source_scene: str = "manual_log_upload",
        recommendation_file_name: str = "",
        perm_open_access: bool = False,
    ) -> dict[str, str]:
        from apps.cases.services import CaseFolderBindingService
        from apps.core.dependencies import (
            build_case_service_with_deps,
            build_client_service,
            build_contract_query_service,
            build_document_service,
        )

        resolved_source = str(source_subfolder or "").strip()
        if not resolved_source and log is not None:
            resolved_source = str(getattr(log, "source_subfolder", "") or "").strip()
        resolved_file_name = str(recommendation_file_name or file_name or "").strip()

        service = CaseFolderBindingService(
            document_service=build_document_service(),
            case_service=build_case_service_with_deps(
                contract_service=build_contract_query_service(),
                client_service=build_client_service(),
            ),
        )
        return service.recommend_bound_subdir_for_log_attachment(
            owner_id=case_id,
            source_subfolder=resolved_source,
            file_name=resolved_file_name,
            source_scene=source_scene,
            perm_open_access=perm_open_access,
        )

    def _resolve_target_subdir(
        self,
        *,
        case_id: int,
        target_subdir: str = "",
        log: Any | None = None,
        file_name: str = "",
        source_scene: str = "manual_log_upload",
        recommendation_file_name: str = "",
        perm_open_access: bool = False,
    ) -> str:
        normalized = str(target_subdir or "").strip()
        if normalized:
            return normalized
        auto_subdir = self._is_auto_subdir_enabled()
        if not auto_subdir:
            return ""
        recommendation = self.recommend_attachment_subdir(
            case_id=case_id,
            log=log,
            file_name=file_name,
            source_scene=source_scene,
            recommendation_file_name=recommendation_file_name,
            perm_open_access=perm_open_access,
        )
        return str(recommendation.get("recommended_subdir") or self.DEFAULT_SUBDIR)

    @staticmethod
    def _is_auto_subdir_enabled() -> bool:
        return SystemConfigService().get_value("CASE_LOG_ATTACHMENT_AUTO_SUBDIR", "true").lower() in (
            "true",
            "1",
            "yes",
        )

    def save_attachment(
        self,
        uploaded_file: Any,
        *,
        case_id: int,
        target_subdir: str = "",
        log: Any | None = None,
        allowed_extensions: list[str] | None = None,
        max_size_bytes: int = 50 * 1024 * 1024,
        file_validator: Any | None = None,
        source_scene: str = "manual_log_upload",
        recommendation_file_name: str = "",
        perm_open_access: bool = False,
    ) -> StoredBusinessFile:
        enabled = self._is_auto_subdir_enabled()
        resolved_recommendation_file_name = str(
            recommendation_file_name or getattr(uploaded_file, "name", "") or ""
        ).strip()
        return self._business_storage_service.save_uploaded_file(
            uploaded_file=uploaded_file,
            purpose="log_attachment",
            case_id=case_id if enabled else None,
            target_subdir=self._resolve_target_subdir(
                case_id=case_id,
                target_subdir=target_subdir,
                log=log,
                file_name=str(getattr(uploaded_file, "name", "") or ""),
                source_scene=source_scene,
                recommendation_file_name=resolved_recommendation_file_name,
                perm_open_access=perm_open_access,
            ),
            allowed_extensions=allowed_extensions,
            max_size_bytes=max_size_bytes,
            file_validator=file_validator,
            use_uuid_name=False,
        )

    def resolve_attachment(self, attachment: Any) -> ResolvedBusinessFile:
        return self._business_storage_service.resolve_file(attachment)

    def move_attachment(
        self,
        attachment: Any,
        *,
        case_id: int,
        target_subdir: str = "",
    ) -> StoredBusinessFile:
        enabled = self._is_auto_subdir_enabled()
        return self._business_storage_service.move_existing_file(
            attachment,
            purpose="log_attachment",
            case_id=case_id if enabled else None,
            target_subdir=self._resolve_target_subdir(
                case_id=case_id,
                target_subdir=target_subdir,
                log=getattr(attachment, "log", None),
            ),
            preferred_filename=getattr(attachment, "original_filename", ""),
        )

    def delete_attachment_file(self, attachment_or_path: Any) -> bool:
        try:
            return self._business_storage_service.delete_file(attachment_or_path)
        except Exception:
            logger.error("删除案件日志附件文件失败: %s", attachment_or_path, exc_info=True)
            return False
