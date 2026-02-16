"""Business logic services."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import ClassVar

from apps.core.filesystem.folder_node_path import normalize_folder_node_path
from apps.core.protocols import IDocumentTemplateBindingService

logger = logging.getLogger("apps.contracts")


@dataclass(frozen=True)
class ContractSubdirPathResolver:
    template_binding_service: IDocumentTemplateBindingService | None

    SUBDIR_KEY_TO_CONTRACT_SUB_TYPE: ClassVar = {
        "contract_documents": "contract",
        "supplementary_agreements": "supplementary_agreement",
    }

    def resolve(self, *, case_type: str, subdir_key: str) -> str | None | None:
        contract_sub_type = self.SUBDIR_KEY_TO_CONTRACT_SUB_TYPE.get(subdir_key)
        if not contract_sub_type:
            return None

        if self.template_binding_service is None:
            return None

        try:
            folder_node_path = self.template_binding_service.get_contract_subdir_path_internal(
                case_type=case_type,
                contract_sub_type=contract_sub_type,
            )
            if not folder_node_path:
                return None
            return normalize_folder_node_path(folder_node_path)
        except Exception:
            logger.exception(
                "resolve_contract_subdir_path_failed", extra={"case_type": case_type, "subdir_key": subdir_key}
            )
            raise
