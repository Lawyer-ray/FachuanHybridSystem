"""Business logic services."""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import NotFoundError, ValidationException

from ..wiring import (
    get_contract_folder_binding_service,
    get_contract_generation_service,
    get_supplementary_agreement_generation_service,
)


class ContractAdminDocumentService:
    def generate_contract_document(self, contract_id: int) -> dict[str, Any]:
        service = get_contract_generation_service()
        content, filename, error = service.generate_contract_document(contract_id)

        if error:
            if "不存在" in error:
                raise NotFoundError(message=error, code="CONTRACT_NOT_FOUND", errors={})
            raise ValidationException(message=error, code="CONTRACT_GENERATION_FAILED", errors={})

        folder_binding_service = get_contract_folder_binding_service()
        binding = folder_binding_service.get_binding(contract_id)

        return {
            "content": content,
            "filename": filename,
            "folder_path": binding.folder_path if binding else None,
        }

    def generate_supplementary_agreement(self, contract_id: int, agreement_id: int) -> dict[str, Any]:
        service = get_supplementary_agreement_generation_service()
        content, filename, error = service.generate_supplementary_agreement(contract_id, agreement_id)

        if error:
            if "不存在" in error:
                raise NotFoundError(message=error, code="SUPPLEMENTARY_AGREEMENT_NOT_FOUND", errors={})
            raise ValidationException(message=error, code="SUPPLEMENTARY_AGREEMENT_GENERATION_FAILED", errors={})

        folder_binding_service = get_contract_folder_binding_service()
        binding = folder_binding_service.get_binding(contract_id)

        return {
            "content": content,
            "filename": filename,
            "folder_path": binding.folder_path if binding else None,
        }
