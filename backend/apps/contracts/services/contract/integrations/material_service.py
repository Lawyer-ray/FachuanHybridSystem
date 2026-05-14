"""Contract finalized material storage service."""

from __future__ import annotations

import logging
from typing import Any

from apps.contracts.models import MaterialCategory
from apps.core.services import BusinessFileStorageService, ResolvedBusinessFile, StoredBusinessFile

logger = logging.getLogger(__name__)


class MaterialService:
    _DEFAULT_SUBDIR = "合同附件"
    _CATEGORY_TO_ARCHIVE_ITEM: dict[str, tuple[str, str]] = {
        MaterialCategory.CONTRACT_ORIGINAL: ("lt_4", "委托合同、风险告知书"),
        MaterialCategory.SUPPLEMENTARY_AGREEMENT: ("lt_4", "委托合同、风险告知书"),
        MaterialCategory.INVOICE: ("lt_5", "收费凭证"),
        MaterialCategory.ARCHIVE_DOCUMENT: ("lt_10", "调查材料等案件关联材料"),
        MaterialCategory.SUPERVISION_CARD: ("lt_18", "办案服务质量监督卡"),
        MaterialCategory.AUTHORIZATION_MATERIAL: ("lt_20", "授权委托证明材料"),
        MaterialCategory.CASE_MATERIAL: ("lt_10", "调查材料等案件关联材料"),
        MaterialCategory.ARCHIVE_UPLOAD: ("lt_10", "调查材料等案件关联材料"),
    }

    def __init__(self, business_storage_service: BusinessFileStorageService | None = None) -> None:
        self._business_storage_service = business_storage_service or BusinessFileStorageService()

    def save_business_material_file(
        self,
        uploaded_file: Any,
        contract_id: int,
        *,
        target_subdir: str = "",
        category: str = "",
        allowed_extensions: list[str] | None = None,
        max_size_bytes: int = 100 * 1024 * 1024,
    ) -> StoredBusinessFile:
        """Save a finalized material file under the contract business root."""
        resolved_subdir = self._resolve_target_subdir(
            contract_id=contract_id,
            category=category,
            target_subdir=target_subdir,
            file_name=str(getattr(uploaded_file, "name", "") or ""),
        )
        return self._business_storage_service.save_uploaded_file(
            uploaded_file=uploaded_file,
            purpose="finalized_material",
            contract_id=contract_id,
            target_subdir=resolved_subdir,
            allowed_extensions=allowed_extensions or [".pdf"],
            max_size_bytes=max_size_bytes,
        )

    def save_material_file(
        self,
        uploaded_file: Any,
        contract_id: int,
        *,
        target_subdir: str = "",
        category: str = "",
    ) -> StoredBusinessFile:
        """Backward-compatible PDF-only helper."""
        return self.save_business_material_file(
            uploaded_file=uploaded_file,
            contract_id=contract_id,
            target_subdir=target_subdir,
            category=category,
            allowed_extensions=[".pdf"],
            max_size_bytes=100 * 1024 * 1024,
        )

    def resolve_material_file(self, material: Any) -> ResolvedBusinessFile:
        return self._business_storage_service.resolve_file(material)

    def move_material_file(
        self,
        material: Any,
        *,
        contract_id: int,
        target_subdir: str = "",
        category: str = "",
    ) -> StoredBusinessFile:
        resolved_subdir = self._resolve_target_subdir(
            contract_id=contract_id,
            category=category or str(getattr(material, "category", "") or ""),
            target_subdir=target_subdir,
            file_name=str(getattr(material, "original_filename", "") or ""),
        )
        return self._business_storage_service.move_existing_file(
            material,
            purpose="finalized_material",
            contract_id=contract_id,
            target_subdir=resolved_subdir,
            preferred_filename=getattr(material, "original_filename", ""),
        )

    def delete_material_file(self, material_or_file_path: Any) -> bool:
        """Delete finalized material physical file."""
        try:
            return self._business_storage_service.delete_file(material_or_file_path)
        except Exception:
            logger.error("删除归档材料文件失败: %s", material_or_file_path, exc_info=True)
            return False

    def _resolve_target_subdir(self, *, contract_id: int, category: str, target_subdir: str, file_name: str = "") -> str:
        normalized_subdir = str(target_subdir or "").strip()
        if normalized_subdir:
            return normalized_subdir

        normalized_category = str(category or "").strip()
        if not normalized_category:
            return self._DEFAULT_SUBDIR

        try:
            from apps.contracts.services.folder.folder_binding_service import FolderBindingService
            from apps.core.dependencies.documents import build_document_template_binding_service

            folder_binding_service = FolderBindingService(
                document_template_binding_service=build_document_template_binding_service(),
            )
            result = folder_binding_service.recommend_bound_subdir_for_material_category(
                owner_id=contract_id,
                material_category=normalized_category,
                file_name=str(file_name or ""),
            )
            recommended_subdir = str(result.get("recommended_subdir") or "").strip()
            if recommended_subdir:
                return recommended_subdir
        except Exception:
            logger.exception(
                "contract_material_recommend_subdir_failed",
                extra={"contract_id": contract_id, "category": category},
            )

        return self._DEFAULT_SUBDIR
