"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any

from apps.core.dtos import SupplementaryAgreementDTO

logger = logging.getLogger("apps.contracts")


class SupplementaryAgreementQueryService:
    def get_supplementary_agreements_internal(self, contract_id: int) -> list[SupplementaryAgreementDTO]:
        try:
            from apps.contracts.models import SupplementaryAgreement

            agreements = SupplementaryAgreement.objects.filter(contract_id=contract_id).order_by("-created_at")
            return [
                SupplementaryAgreementDTO(
                    id=agreement.id,
                    contract_id=agreement.contract_id,
                    title=agreement.name or "",
                    content=None,
                    signed_date=None,
                    file_path=None,
                    created_at=str(agreement.created_at) if agreement.created_at else None,
                )
                for agreement in agreements
            ]
        except Exception:
            logger.exception("get_supplementary_agreements_internal_failed", extra={"contract_id": contract_id})
            raise

    def get_supplementary_agreement_model_internal(self, contract_id: int, agreement_id: int) -> Any | None:
        try:
            from apps.contracts.models import SupplementaryAgreement

            return SupplementaryAgreement.objects.prefetch_related("parties__client").get(
                pk=agreement_id, contract_id=contract_id
            )
        except SupplementaryAgreement.DoesNotExist:
            return None
