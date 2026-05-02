"""归档检查清单服务 facade。"""

from __future__ import annotations

from typing import Any

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial

from ..constants import ChecklistItem
from . import case_material_sync as sync_mod
from . import checklist_query as query_mod


class ArchiveChecklistService:
    """归档检查清单服务"""

    def get_checklist_with_status(self, contract: Contract) -> dict[str, Any]:
        return query_mod.get_checklist_with_status(contract)

    def get_case_material_match_map(self, contract: Contract) -> dict[str, Any]:
        return sync_mod.get_case_material_match_map(contract)

    def sync_case_materials_to_archive(
        self,
        contract: Contract,
        archive_item_codes: list[str] | None = None,
        case_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        return sync_mod.sync_case_materials_to_archive(contract, archive_item_codes, case_ids)

    def reset_and_resync_case_materials(
        self,
        contract: Contract,
        archive_item_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        return sync_mod.reset_and_resync_case_materials(contract, archive_item_codes)

    def upload_material_to_archive_item(
        self,
        contract: Contract,
        archive_item_code: str,
        uploaded_file: Any,
    ) -> FinalizedMaterial:
        return sync_mod.upload_material_to_archive_item(contract, archive_item_code, uploaded_file)

    def get_template_items(self, archive_category: str) -> list[ChecklistItem]:
        return query_mod.get_template_items(archive_category)

    def get_auto_detect_items(self, archive_category: str) -> list[ChecklistItem]:
        return query_mod.get_auto_detect_items(archive_category)
